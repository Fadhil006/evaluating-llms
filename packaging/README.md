# Desktop builds

The GitHub Actions workflow builds a standalone executable on native Windows and
Linux runners. Download the artifact for your operating system from the
workflow run; Windows gets `LLMComparisonLab.exe`, Linux gets
`LLMComparisonLab` (make it executable with `chmod +x` if needed).

Run the file to start the local API and worker; it opens the app in your default
browser. Close the terminal/window running it to stop the app. The first run
uses demo mode and creates local files in:

- Windows: `%LOCALAPPDATA%\LLMComparisonLab`
- Linux: `${XDG_DATA_HOME:-~/.local/share}/LLMComparisonLab`

To use live provider requests, edit the `.env` file in that directory, set
`EXECUTION_MODE=live`, and add provider keys. Restart the app afterward. Never
share that file: it contains credentials. Data remains local and is not
included in the executable.

Build locally from the repository root after building the frontend and
installing backend dependencies plus PyInstaller:

```sh
cd frontend && npm ci && npm run build
cd .. && python -m pip install ./backend pyinstaller
python -m PyInstaller --noconfirm --clean packaging/desktop.spec
```

Build each executable on its target OS. The Windows executable must be built
on Windows; the Linux executable must be built on Linux. Linux builds target
the Ubuntu runner's x86_64 environment and may not run on every distribution.
