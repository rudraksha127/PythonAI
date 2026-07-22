# ForgeAI Capture — VS Code Extension

Captures AI coding assistant **accept/reject/edit signals** and writes them to the ForgeAI CaptureEngine SQLite database, completing the signal collection loop for self-improving fine-tuning (MIT SEAL architecture).

## How It Works

```
Editor Context → CompletionProvider → Inline Suggestion
                     ↓
              Accept / Reject / Edit
                     ↓
              CaptureEngine (SQLite DB)
                     ↓
           Python GRPO Training Pipeline
```

1. **Inline Completions**: The extension provides contextual inline code suggestions as you type
2. **Signal Detection**: When you accept (Tab), reject (Esc), or edit a suggestion, the signal is detected
3. **Database Storage**: The signal is written to `~/.forgeai/signals.db` — the same database the Python CaptureEngine uses
4. **Training**: The ForgeAI training pipeline reads these signals to fine-tune models with GRPO

## Features

- ✅ **Accept Tracking**: Detects when suggestions are accepted as-is
- ✅ **Reject Tracking**: Detects when suggestions are dismissed
- ✅ **Edit Tracking**: Detects when suggestions are modified before accepting
- ✅ **SQLite Storage**: Writes to the same schema as the Python CaptureEngine
- ✅ **Session Management**: Tracks VS Code sessions for analytics
- ✅ **Status Bar Indicator**: Shows capture status at a glance
- ✅ **Configurable**: Control what signals to capture and where to store them

## Installation

### From VS Code Marketplace (future)

Search for "ForgeAI Capture" in the Extensions view.

### From VSIX (development)

```bash
# Build the extension
cd tools/vscode-forgeai-capture
npm install
npm run compile

# Package
npm install -g @vscode/vsce
vsce package

# Install in VS Code
code --install-extension forgeai-capture-*.vsix
```

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `forgeai.dbPath` | `~/.forgeai/signals.db` | Path to the SQLite signals database |
| `forgeai.projectName` | (workspace name) | Project name for session identification |
| `forgeai.enabled` | `true` | Enable/disable signal capture |
| `forgeai.captureRejects` | `true` | Capture reject signals |
| `forgeai.captureEdits` | `true` | Capture edit signals |

## Commands

- **ForgeAI: Show Capture Status** — View signal counts and database info
- **ForgeAI: Export Captured Signals** — Export signals for training
- **ForgeAI: Toggle Signal Capture** — Enable/disable capture on the fly

## Database Schema

The extension writes to the same SQLite schema as the Python `CaptureEngine`:

- `signals` — Individual accept/reject/edit events with full context
- `sessions` — Editor session tracking with per-session statistics
- `acceptance_metrics` — Daily aggregate acceptance rates
- `training_runs` — Model fine-tuning run metadata

## Signal Types

| Signal | Description | Training Use |
|--------|-------------|--------------|
| `accept` | Suggestion accepted as-is | Positive example for SFT |
| `reject` | Suggestion dismissed | Negative example for DPO/GRPO |
| `edit` | Suggestion modified before accept | Paired example for GRPO |

## Development

```bash
cd tools/vscode-forgeai-capture
npm install
npm run compile    # Build TypeScript
npm run watch     # Watch mode for development
```

## Integration with Python Pipeline

Signals captured by this extension are automatically available to the ForgeAI Python training pipeline:

```bash
# View capture statistics
python -m src.cli forge stats

# Export signals for training
python -m src.cli forge dashboard --demo

# Train with GRPO using captured signals
python -m src.cli grpo train --data ~/.forgeai/signals.db
```

## License

MIT
