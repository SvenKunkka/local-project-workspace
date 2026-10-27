# Project Workspace

[简体中文](README.md) | **English**

A local-first project management workspace with task views, AI-assisted scheduling, and collaboration over a local network. It was independently developed based on features publicly presented in [the original post](https://www.xiaohongshu.com/explore/6adca1440000000024035ec5). It is not the original author's software, and its internal behavior and feature details may differ.

[Download releases](https://github.com/SvenKunkka/local-project-workspace/releases)

## Getting started

- **macOS:** Open the DMG and drag Project Workspace into Applications. The existing build requires Apple Silicon and macOS 26 or later.
- **Windows:** Extract the Windows archive and run `ProjectWorkspace.exe`. The build requires Windows 10/11 x64 and the Microsoft Edge WebView2 Runtime.
- **Linux:** Extract the Linux archive and run `ProjectWorkspace/ProjectWorkspace` from a graphical desktop. The build targets Ubuntu 24.04 x86_64; other distributions require compatible Qt and graphics libraries. Notifications require `notify-send` and a working desktop notification service.

On macOS, choose whether to allow notifications when prompted. If permission is denied, due reminders are retained and processed while the app is running after permission is granted.

Data is stored locally:

- macOS: `~/.local/share/local-project-manager/`
- Linux: `$XDG_DATA_HOME/local-project-manager/` (default: `~/.local/share/local-project-manager/`)
- Windows: `%LOCALAPPDATA%\LocalProjectWorkspace\`

A timestamped SQLite backup is created before a database upgrade. The interface can export JSON and import it as a separate copy without overwriting existing projects. Member identities and credentials are not restored with the copy.

Tasks support projects, list and draggable kanban views, tag filters, Gantt charts, multiple assignees, subtasks, planned and actual dates, priorities, overdue indicators, status history, and daily or weekly reports. The AI assistant connects to an OpenAI-compatible endpoint; proposed changes must be confirmed individually before they are applied. The API address must include its version path, for example `http://127.0.0.1:11434/v1` for a local Ollama service. When you send a prompt, the current filtered tasks and project list are sent to the configured model provider. The API key remains in the current page's memory. The activity chart covers status changes recorded after the upgrade; it does not reconstruct earlier history.

## Local-network collaboration

Sharing is off by default. The host turns it on in **Local Network Collaboration** and issues invitation links. Members can open a link in a browser or enter it under **Local Network Collaboration → Join another host** in the desktop app. Use the app menu or collaboration-page button to return to the local workspace. Host, administrator, editor, and read-only member roles have different permissions. Sharing stops when the host app closes and must be enabled again after restart. When disconnected, the current page retains loaded content, prevents edits, and retries the connection automatically.

LAN traffic uses unencrypted HTTP, and invitation links are reusable access credentials. Use them only on a trusted local network and share links privately; the host can revoke member access. Editing locks expire after 120 seconds of disconnection. One cross-device connection and task-edit test has been completed; complex concurrent use and security auditing have not been completed. Do not use the feature for sensitive data until those limitations are addressed.

## Reminders and limitations

Reminders can fire once at the specified time, 30 minutes in advance and again at the specified time, or daily. The desktop app must be running and system notifications must be permitted. Reminders are not delivered on time while the app is closed or the computer is asleep; overdue reminders are processed when the app runs again. After joining a host through the desktop app, a member receives reminders for tasks whose assignee field includes the member's name. Separate multiple names with commas.

Windows submits notifications through PowerShell; Linux uses `notify-send`. Successful submission does not guarantee that the operating system displays a notification. The browser version does not provide system notifications. Daily and weekly reports summarize current tasks and update records; they are not a complete historical audit.

The Mac application uses an ad hoc signature and has not been signed with an Apple Developer certificate or notarized, so macOS may block it. The Windows build is unsigned and may trigger SmartScreen. Actual system-notification display has not yet been verified because notifications were disabled on the test machine.

## Run and test from source

Python 3 is required. For the browser version, run `python3 server.py` from the project directory and open `http://127.0.0.1:8765`. Stopping the process stops the service. Run `python3 test_integration.py` to execute the API tests with a temporary database.

The macOS shell is in `MacApp.m` and can be built with macOS command-line developer tools and PyInstaller. The Windows and Linux shell is `desktop.py`: install `pywebview` on Windows or `pywebview[qt]` on Linux, then run `python -m PyInstaller desktop.spec`. Building also requires `pyinstaller` and `certifi`. Run `python test_desktop.py` to test desktop-bridge and reminder-acknowledgment logic. Build artifacts are not included in the source repository.
