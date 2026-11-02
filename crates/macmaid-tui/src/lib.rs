pub mod input;
pub mod state;
pub mod ui;

use crossterm::event::{self, Event, KeyEventKind};
use crossterm::execute;
use crossterm::terminal::{
    disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen,
};
use ratatui::backend::CrosstermBackend;
use ratatui::Terminal;
use state::AppState;
use std::io::{self, stdout};
use std::time::Duration;

/// Entrypoint to run the interactive full-screen Ratatui TUI.
pub fn run() -> io::Result<()> {
    // MacMaid must never run as root
    if unsafe { libc::geteuid() } == 0 {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "MacMaid must never run as root",
        ));
    }

    enable_raw_mode()?;
    let mut out = stdout();
    execute!(out, EnterAlternateScreen)?;
    let backend = CrosstermBackend::new(out);
    let mut terminal = Terminal::new(backend)?;

    let mut state = AppState::new();
    state.refresh_system_metrics();

    let res = run_loop(&mut terminal, &mut state);

    // Restore terminal cleanly
    let _ = disable_raw_mode();
    let _ = execute!(terminal.backend_mut(), LeaveAlternateScreen);
    let _ = terminal.show_cursor();

    res
}

fn run_loop<B: ratatui::backend::Backend>(
    terminal: &mut Terminal<B>,
    state: &mut AppState,
) -> io::Result<()> {
    loop {
        terminal
            .draw(|f| ui::render(f, state))
            .map_err(|e| io::Error::other(e.to_string()))?;

        if event::poll(Duration::from_millis(50))? {
            if let Event::Key(key) = event::read()? {
                if key.kind == KeyEventKind::Press {
                    let should_continue = input::handle_key(state, key);
                    if !should_continue {
                        break;
                    }
                }
            }
        }
    }
    Ok(())
}
