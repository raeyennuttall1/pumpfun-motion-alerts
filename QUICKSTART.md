# Quick Start Guide

Get up and running with the Pump.fun Motion Alert System in 5 minutes.

## Prerequisites

- Python 3.9 or higher
- pip (Python package manager)
- Internet connection

## Installation

### Step 1: Install Dependencies

Open a terminal in the project directory and run:

```bash
pip install -r requirements.txt
```

This will install all required packages. Takes about 2-3 minutes.

### Step 2: Verify Installation

Run the test script to ensure everything is installed correctly:

```bash
python scripts/test_setup.py
```

You should see:
```
✓ All dependencies installed
✓ Database created successfully
✓ System ready!
```

## Running the System

### Option 1: Real-time Monitoring (Recommended)

Start monitoring Pump.fun in real-time:

```bash
python main.py
```

What happens:
1. Connects to Pump.fun WebSocket
2. Monitors new token launches
3. Tracks trades and calculates features
4. Triggers motion alerts when criteria met
5. Automatically labels alerts with future outcomes

**Let this run for at least 24 hours** to collect initial data.

**To stop:** Press `Ctrl+C`

### Option 2: Test Mode (No Live Connection)

If you want to test without connecting to Pump.fun:

```bash
python scripts/test_system.py
```

This creates mock data to verify the system works.

## Understanding Output

When running, you'll see logs like:

```
2024-01-15 10:30:45 | INFO | New token detected: PUMP (7xKXt...)
2024-01-15 10:31:02 | INFO | 🚨 MOTION ALERT: 7xKXt... - MC: $45,230
```

When an alert triggers, you'll see a detailed summary:

```
╔══════════════════════════════════════╗
║       MOTION ALERT TRIGGERED         ║
╚══════════════════════════════════════╝

Token: PUMP (PumpCoin)
Buy Volume: 12.50 SOL
Unique Buyers: 45
Known Wallets: 5
```

This means the system detected strong momentum for that token.

## After 24 Hours

### 1. Label Your Alerts

After collecting alerts, label them with outcomes:

```bash
python scripts/label_alerts.py
```

This checks how each alert performed (did it pump?).

### 2. Analyze Performance

View your alert hit rates:

```bash
python scripts/analyze_alerts.py
```

Output shows:
- Hit rate (% of alerts that pumped)
- Average returns
- Best performers
- CSV export for further analysis

### 3. Adjust Thresholds (Optional)

Edit `config.yaml` to tune alert sensitivity:

```yaml
motion_alert:
  min_buy_volume_sol: 10.0      # Lower = more alerts
  min_unique_buyers: 30         # Lower = more alerts
  max_market_cap: 100000        # Higher = more alerts
```

Restart the system after changes.

## After 1 Week (50+ Labeled Alerts)

### Train ML Model

Once you have enough data:

```bash
python scripts/train_model.py
```

This trains a neural network to predict which alerts will pump.

## Common Issues

### "Module not found"

**Solution:** Install dependencies
```bash
pip install -r requirements.txt
```

### "No alerts triggering"

**Solutions:**
1. Lower thresholds in `config.yaml`
2. Wait longer (market may be slow)
3. Check that system is connected to Pump.fun

### "WebSocket disconnected"

**Solution:** System auto-reconnects. If persisting:
1. Check internet connection
2. Pump.fun API may be down (try again later)

### Database errors

**Solution:** Delete database and restart
```bash
rm -rf data/pumpfun_alerts.db  # Linux/Mac
del data\pumpfun_alerts.db     # Windows
python main.py
```

## File Locations

- **Database**: `data/pumpfun_alerts.db`
- **Logs**: `logs/pumpfun_alerts.log`
- **Config**: `config.yaml`
- **Trained models**: `models/best_model.pt`

## Next Steps

1. **Read the full README.md** for detailed documentation
2. **Customize alert thresholds** based on your strategy
3. **Experiment with ML models** after collecting data
4. **Build custom integrations** (Discord bot, auto-trading, etc.)

## Tips

- **Let it run continuously** for best data collection
- **Start conservative** with thresholds (avoid too many false positives)
- **Paper trade first** before using real funds
- **Memecoin trading is risky** - use at your own risk

## Support

- Check `README.md` for full documentation
- Review `config.yaml` for all settings
- Inspect `logs/pumpfun_alerts.log` for debugging

---

**You're ready to go! Run `python main.py` to start. 🚀**
