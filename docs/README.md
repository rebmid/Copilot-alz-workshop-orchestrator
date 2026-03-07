# Documentation

This folder contains supplementary documentation, presentation materials, and demo assets for the Copilot ALZ Workshop Orchestrator.

## Contents

| File | Description |
|---|---|
| [azure-provider-requirements.md](azure-provider-requirements.md) | Required Azure resource providers and signal coverage details |
| [workshop-mode.md](workshop-mode.md) | Copilot workshop session documentation |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contribution guidelines |
| [summary.md](summary.md) | Project summary |
| [options-5-6.md](options-5-6.md) | Implementation options reference |
| `Enterprise-Safe...pptx` | Presentation deck with architecture diagram and business value proposition |
| `GithubCopilot_SDK_ProductFeedback_Jeff_Garcia.png` | SDK product feedback screenshot (bonus submission) |
| `demo/` | Demo screenshots and sample HTML report |

## Architecture

See [ARCHITECTURE.md](../ARCHITECTURE.md) at the project root for the full system architecture.

## Main README

See the [project README](../README.md) for problem statement, solution overview, setup instructions, RAI notes, and full technical documentation.

## Test Suite

```bash
python -m pytest tests/test_workshop.py -v
```
