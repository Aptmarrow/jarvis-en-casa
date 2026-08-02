# J.A.R.V.I.S.

**Just A Really Versatile Intelligent System**

A personal assistant orchestrator for Fedora Linux.

> Jarvis is not the AI — Jarvis is the orchestrator.
> The AI is a replaceable component. Tools are independent modules.
> Specialized agents execute complex tasks. The user always has the final say.

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Run
python -m jarvis
```

## Architecture

```
Voice Interface → AI Orchestrator → Tool Manager → Plugins → Linux System
                       ↕                               ↕
              Context Manager              Agent Orchestrator
              Memory Engine                   Scheduler
              Knowledge Graph
```

## License

MIT
