# ForgeAI VS Code Extension

The official VS Code extension for ForgeAI — the self-improving AI coding assistant.

## Features

- **Capture Accept/Reject Signals**: One-click feedback to train your personal model
- **Real-time Acceptance Rate**: Watch your model improve week over week
- **Context-aware Suggestions**: Powered by cAST RAG for semantic code retrieval
- **Local Privacy**: All signals stored in encrypted local database
- **Test Integration**: Automatic test pass/fail capture for verifiable rewards

## Installation

1. Clone the ForgeAI repository
2. Run `npm install` in this directory
3. Press F5 to launch the Extension Development Host
4. The ForgeAI panel will appear in the sidebar

## Usage

### Capture Signals

When ForgeAI suggests code:
- Click **✓ Accept** if you use it as-is
- Click **✗ Reject** if it's not helpful
- Click **✎ Edit** if you modify it (captures edit distance)

### View Analytics

Open the ForgeAI panel to see:
- Daily acceptance rate
- Improvement over time
- Training data export
- Model retraining triggers

## Development

```bash
# Install dependencies
npm install

# Run the extension
npm run compile
# Then F5 in VS Code

# Package for distribution
npm run package
```

## Architecture

The extension communicates with the ForgeAI Capture Engine via:
- Local SQLite database (`~/.forgeai/signals.db`)
- Encrypted signal storage
- Automatic sync with training pipeline

## License

MIT