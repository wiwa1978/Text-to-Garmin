# text-to-garmin-workout

CLI tool that converts natural language workout descriptions into structured Garmin Connect workouts, powered by GitHub Copilot.

## How it works

1. **You describe a workout** in plain English (e.g., *"W/u, 20min easy, 4x 2min hills @ 10k effort, c/d"*)
2. **Copilot (LLM) parses it** into a structured workout — and asks clarifying questions if anything is ambiguous (e.g., "How much rest between intervals?")
3. **Preview** the workout structure before uploading
4. **Upload** directly to Garmin Connect

## Prerequisites

- **Python 3.10+**
- **GitHub Copilot CLI** installed and authenticated (`copilot auth login`)
- **Garmin Connect** account

## Installation

```bash
git clone <this-repo>
cd text-to-garmin-workout
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -e .
```

## Usage

### Basic (with upload)
```bash
text-to-garmin "W/u, 20min easy, 4x 2min hills @ 10k effort, 4x 1min hills @ 5k effort, 20min easy, c/d"
```

### With a workout name
```bash
text-to-garmin "5x 1km @ 5k pace with 90s rest" -n "5x1km VO2max"
```

### Interactive mode (no arguments)
```bash
text-to-garmin
# Will prompt you for the workout description
```

### Preview only (no upload)
```bash
text-to-garmin --no-upload "10x 400m @ mile pace, 200m jog rest"
```

### Rest until lap button
```bash
text-to-garmin --no-upload "6x 2min @ 10k pace, rest until lap button"
```

### Output Garmin JSON only
```bash
text-to-garmin --json-only "3x 2km @ threshold, 2min rest"
```

### Save JSON to file
```bash
text-to-garmin --save workout.json "8x 800m @ 10k effort, 90s rest"
```

## Garmin Authentication

On first use, you'll be prompted for your Garmin Connect email and password. Successful logins are cached in `~/.garminconnect/garmin_tokens.json` so future runs can reuse and refresh the session automatically.

If Garmin requires MFA, the CLI will prompt for the one-time code during login.

You can also set credentials via environment variables:
```bash
export GARMIN_EMAIL="you@example.com"
export GARMIN_PASSWORD="your-password"
```

## What it understands

The LLM parser handles common running workout notation:

| Notation | Meaning |
|----------|---------|
| `W/u`, `WU` | Warmup |
| `C/d`, `CD` | Cooldown |
| `easy`, `E` | Easy effort |
| `tempo`, `T` | Tempo effort |
| `threshold`, `LT` | Lactate threshold |
| `10k`, `5k`, `mile` | Race pace efforts |
| `4x 2min` | 4 repetitions of 2 minutes |
| `hills` | Hill intervals |
| `strides` | Short fast accelerations |
| `strength` | Strength/conditioning work |
| `R`, `rest` | Recovery between intervals |
| `rest until lap button` | Recovery until you press lap |

### Smart clarifications

If your workout description is ambiguous, Copilot will ask follow-up questions:

```
> text-to-garmin "4x 800m @ 5k pace"

Copilot: How much rest/recovery would you like between the 800m intervals?

Your answer: 2 minutes jog
```

## Example output

```
🏃 Hill Repeats (running)
  1. 🔥 Warmup (until lap button)
  2. 🏃 Run 20:00 @ easy
  3. 🔄 Repeat 4x:
     a. ⚡ Interval 2:00 @ 10k
     b. 😴 Rest 1:00
  4. 🔄 Repeat 4x:
     a. ⚡ Interval 1:00 @ 5k
     b. 😴 Rest 1:00
  5. 🏃 Run 20:00 @ easy
  6. ❄️ Cooldown (until lap button)
```

Lap-button recovery steps are previewed as:
`😴 Rest (until lap button)`

## Architecture

```
Natural language input
    → GitHub Copilot SDK (LLM parsing + Q&A)
    → Pydantic workout models (validation)
    → Garmin Connect JSON builder
    → Upload via garminconnect library (native token-based auth)
```

## License

MIT
