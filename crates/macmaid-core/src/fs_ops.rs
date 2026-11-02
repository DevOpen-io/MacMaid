use std::ffi::{CStr, CString};
use std::fs;
use std::io;
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::MetadataExt;
use std::os::unix::io::RawFd;
use std::path::{Component, Path, PathBuf};

use crate::safety::{dirs_home, PathSafetyError};

pub struct DirFdGuard(RawFd);

impl DirFdGuard {
    pub fn fd(&self) -> RawFd {
        self.0
    }
}

impl Drop for DirFdGuard {
    fn drop(&mut self) {
        if self.0 >= 0 {
            unsafe {
                libc::close(self.0);
            }
        }
    }
}

/// Open every directory component without following links, pinning the parent descriptor.
pub fn directory_fd(path: &Path) -> io::Result<DirFdGuard> {
    if !path.is_absolute() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "absolute lexical directory required",
        ));
    }

    let root_c = CString::new("/").unwrap();
    let mut current_fd = unsafe { libc::open(root_c.as_ptr(), libc::O_RDONLY | libc::O_DIRECTORY) };
    if current_fd < 0 {
        return Err(io::Error::last_os_error());
    }

    for component in path.components() {
        match component {
            Component::RootDir => {}
            Component::Normal(c) => {
                let bytes = c.as_bytes();
                if bytes.contains(&0) {
                    unsafe {
                        libc::close(current_fd);
                    }
                    return Err(io::Error::new(
                        io::ErrorKind::InvalidInput,
                        "null byte in component",
                    ));
                }
                let c_name = CString::new(bytes).unwrap();
                let next_fd = unsafe {
                    libc::openat(
                        current_fd,
                        c_name.as_ptr(),
                        libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW,
                    )
                };
                unsafe {
                    libc::close(current_fd);
                }
                if next_fd < 0 {
                    return Err(io::Error::last_os_error());
                }
                current_fd = next_fd;
            }
            _ => {
                unsafe {
                    libc::close(current_fd);
                }
                return Err(io::Error::new(
                    io::ErrorKind::InvalidInput,
                    "invalid path component in directory_fd",
                ));
            }
        }
    }

    Ok(DirFdGuard(current_fd))
}

/// Deletion anchored to a no-follow directory descriptor.
pub fn remove_validated_path<F>(path: &Path, authorize: F) -> io::Result<()>
where
    F: Fn() -> Result<(), PathSafetyError>,
{
    let parent = path
        .parent()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "path has no parent"))?;
    let file_name = path
        .file_name()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "path has no file name"))?;
    let c_name = CString::new(file_name.as_bytes())
        .map_err(|e| io::Error::new(io::ErrorKind::InvalidInput, e))?;

    let dir_guard = directory_fd(parent)?;
    let dir_fd = dir_guard.fd();

    authorize().map_err(|e| io::Error::new(io::ErrorKind::PermissionDenied, e.to_string()))?;

    let mut stat_buf: libc::stat = unsafe { std::mem::zeroed() };
    let res = unsafe {
        libc::fstatat(
            dir_fd,
            c_name.as_ptr(),
            &mut stat_buf,
            libc::AT_SYMLINK_NOFOLLOW,
        )
    };
    if res != 0 {
        let err = io::Error::last_os_error();
        if err.kind() == io::ErrorKind::NotFound {
            return Ok(());
        }
        return Err(err);
    }

    let uid = unsafe { libc::getuid() };
    if stat_buf.st_uid != uid {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "target is not owned by the current user",
        ));
    }

    let is_dir = (stat_buf.st_mode & libc::S_IFMT) == libc::S_IFDIR;
    if is_dir {
        // Open target directory descriptor and recursively remove contents
        remove_dir_contents_fd(dir_fd, &c_name)?;
        let rmdir_res = unsafe { libc::unlinkat(dir_fd, c_name.as_ptr(), libc::AT_REMOVEDIR) };
        if rmdir_res != 0 {
            return Err(io::Error::last_os_error());
        }
    } else {
        let unlink_res = unsafe { libc::unlinkat(dir_fd, c_name.as_ptr(), 0) };
        if unlink_res != 0 {
            return Err(io::Error::last_os_error());
        }
    }

    // Verify post-condition
    let verify_res = unsafe {
        libc::fstatat(
            dir_fd,
            c_name.as_ptr(),
            &mut stat_buf,
            libc::AT_SYMLINK_NOFOLLOW,
        )
    };
    if verify_res == 0 {
        return Err(io::Error::other("target still exists after deletion"));
    }

    Ok(())
}

fn remove_dir_contents_fd(parent_fd: RawFd, dir_name: &CStr) -> io::Result<()> {
    let child_dir_fd = unsafe {
        libc::openat(
            parent_fd,
            dir_name.as_ptr(),
            libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW,
        )
    };
    if child_dir_fd < 0 {
        return Err(io::Error::last_os_error());
    }
    let child_guard = DirFdGuard(child_dir_fd);

    let dup_fd = unsafe { libc::dup(child_guard.fd()) };
    if dup_fd < 0 {
        return Err(io::Error::last_os_error());
    }
    let dir_stream = unsafe { libc::fdopendir(dup_fd) };
    if dir_stream.is_null() {
        unsafe {
            libc::close(dup_fd);
        }
        return Err(io::Error::last_os_error());
    }

    struct DirStreamGuard(*mut libc::DIR);
    impl Drop for DirStreamGuard {
        fn drop(&mut self) {
            if !self.0.is_null() {
                unsafe {
                    libc::closedir(self.0);
                }
            }
        }
    }
    let _stream_guard = DirStreamGuard(dir_stream);

    loop {
        let entry = unsafe { libc::readdir(dir_stream) };
        if entry.is_null() {
            break;
        }
        let d_name = unsafe { CStr::from_ptr((*entry).d_name.as_ptr()) };
        let name_bytes = d_name.to_bytes();
        if name_bytes == b"." || name_bytes == b".." {
            continue;
        }

        let mut stat_buf: libc::stat = unsafe { std::mem::zeroed() };
        let res = unsafe {
            libc::fstatat(
                child_guard.fd(),
                d_name.as_ptr(),
                &mut stat_buf,
                libc::AT_SYMLINK_NOFOLLOW,
            )
        };
        if res != 0 {
            continue;
        }

        let is_dir = (stat_buf.st_mode & libc::S_IFMT) == libc::S_IFDIR;
        if is_dir {
            remove_dir_contents_fd(child_guard.fd(), d_name)?;
            unsafe {
                libc::unlinkat(child_guard.fd(), d_name.as_ptr(), libc::AT_REMOVEDIR);
            }
        } else {
            unsafe {
                libc::unlinkat(child_guard.fd(), d_name.as_ptr(), 0);
            }
        }
    }

    Ok(())
}

extern "C" {
    fn renameatx_np(
        fromfd: libc::c_int,
        from: *const libc::c_char,
        tofd: libc::c_int,
        to: *const libc::c_char,
        flags: libc::c_uint,
    ) -> libc::c_int;
}

pub fn move_to_trash_exclusive<F>(path: &Path, destination: &Path, authorize: F) -> io::Result<()>
where
    F: Fn() -> Result<(), PathSafetyError>,
{
    let parent = path
        .parent()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "path has no parent"))?;
    let file_name = path
        .file_name()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "path has no file name"))?;
    let c_source_name = CString::new(file_name.as_bytes())
        .map_err(|e| io::Error::new(io::ErrorKind::InvalidInput, e))?;

    let dest_parent = destination
        .parent()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "destination has no parent"))?;
    let dest_file_name = destination.file_name().ok_or_else(|| {
        io::Error::new(io::ErrorKind::InvalidInput, "destination has no file name")
    })?;
    let c_dest_name = CString::new(dest_file_name.as_bytes())
        .map_err(|e| io::Error::new(io::ErrorKind::InvalidInput, e))?;

    let source_dir = directory_fd(parent)?;
    authorize().map_err(|e| io::Error::new(io::ErrorKind::PermissionDenied, e.to_string()))?;

    let mut source_stat: libc::stat = unsafe { std::mem::zeroed() };
    let res = unsafe {
        libc::fstatat(
            source_dir.fd(),
            c_source_name.as_ptr(),
            &mut source_stat,
            libc::AT_SYMLINK_NOFOLLOW,
        )
    };
    if res != 0 {
        return Err(io::Error::last_os_error());
    }

    let uid = unsafe { libc::getuid() };
    if source_stat.st_uid != uid {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "Trash target changed or is not owned by the current user",
        ));
    }
    if (source_stat.st_mode & libc::S_IFMT) == libc::S_IFLNK {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "symlink Trash target rejected",
        ));
    }

    // Try descriptor-anchored open of destination parent (~/.Trash)
    // If TCC denies directory open of ~/.Trash, fall back to AT_FDCWD (-2) exclusive rename
    let trash_dir_res = directory_fd(dest_parent);
    const RENAME_EXCL: libc::c_uint = 0x00000004;

    match trash_dir_res {
        Ok(trash_dir) => {
            let rename_res = unsafe {
                renameatx_np(
                    source_dir.fd(),
                    c_source_name.as_ptr(),
                    trash_dir.fd(),
                    c_dest_name.as_ptr(),
                    RENAME_EXCL,
                )
            };
            if rename_res != 0 {
                return Err(io::Error::last_os_error());
            }

            let mut moved_stat: libc::stat = unsafe { std::mem::zeroed() };
            let stat_res = unsafe {
                libc::fstatat(
                    trash_dir.fd(),
                    c_dest_name.as_ptr(),
                    &mut moved_stat,
                    libc::AT_SYMLINK_NOFOLLOW,
                )
            };
            if stat_res != 0 {
                return Err(io::Error::last_os_error());
            }

            if (source_stat.st_dev, source_stat.st_ino) != (moved_stat.st_dev, moved_stat.st_ino) {
                return Err(io::Error::other(
                    "Trash target identity changed during move",
                ));
            }
        }
        Err(_) => {
            // Fallback using AT_FDCWD (-2 on macOS)
            authorize()
                .map_err(|e| io::Error::new(io::ErrorKind::PermissionDenied, e.to_string()))?;
            let c_full_source = CString::new(path.as_os_str().as_bytes())
                .map_err(|e| io::Error::new(io::ErrorKind::InvalidInput, e))?;
            let c_full_dest = CString::new(destination.as_os_str().as_bytes())
                .map_err(|e| io::Error::new(io::ErrorKind::InvalidInput, e))?;

            let rename_res = unsafe {
                renameatx_np(
                    -2, // AT_FDCWD
                    c_full_source.as_ptr(),
                    -2, // AT_FDCWD
                    c_full_dest.as_ptr(),
                    RENAME_EXCL,
                )
            };
            if rename_res != 0 {
                return Err(io::Error::last_os_error());
            }

            let dest_meta = fs::symlink_metadata(destination)?;
            if (source_stat.st_dev as u64, source_stat.st_ino as u64)
                != (dest_meta.dev(), dest_meta.ino())
            {
                return Err(io::Error::other(
                    "Trash target identity changed during move",
                ));
            }
        }
    }

    // Verify source no longer exists
    let verify_res = unsafe {
        libc::fstatat(
            source_dir.fd(),
            c_source_name.as_ptr(),
            &mut source_stat,
            libc::AT_SYMLINK_NOFOLLOW,
        )
    };
    if verify_res == 0 {
        return Err(io::Error::other("Trash source still exists after move"));
    }

    Ok(())
}

pub fn unique_trash_destination(path: &Path) -> io::Result<PathBuf> {
    let home = dirs_home()
        .ok_or_else(|| io::Error::new(io::ErrorKind::NotFound, "home directory unavailable"))?;
    let trash = home.join(".Trash");
    let file_name = path
        .file_name()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "path has no file name"))?;
    let name_str = file_name.to_string_lossy();

    let mut candidate = trash.join(&*name_str);
    let mut counter = 1;
    while candidate.exists() || fs::symlink_metadata(&candidate).is_ok() {
        candidate = trash.join(format!("{name_str} {counter}"));
        counter += 1;
    }
    Ok(candidate)
}
