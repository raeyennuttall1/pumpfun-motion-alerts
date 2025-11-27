# Pump.fun Motion Alert System
command for live motion Feed: powershell -command "Get-Content 'logs/pumpfun_alerts.log' -Wait | Select-String -Pattern 'Token:|Buy Volume:|Unique Buyers:|MOTION ALERT'"
command for live full Token Scan Feed: powershell -command "Select-String -Path 'logs/pumpfun_alerts.log' -Pattern 'MOTION ALERT TRIGGERED' -Context 0,15 | Select-Object -Last 3"
A sophisticated real-time trading system for detecting and analyzing trending memecoins on Pump.fun. Uses machine learning to identify high-probability pump opportunities and calculate optimal entry signals.

## Features

- **Real-time Monitoring**: WebSocket-based live tracking of Pump.fun launches and trades
- **Motion Detection**: Configurable alert system based on volume, velocity, and smart money
- **Wallet Intelligence**: Tracks and identifies profitable wallets
- **Outcome Labeling**: Automatically labels alerts with future performance data
- **Hit Rate Analysis**: Comprehensive backtesting and performance metrics
- **ML Prediction**: Deep neural network for pump probability prediction
- **Local Database**: SQLite-based storage for all data (no cloud required)

## System Architecture

```
Pump.fun API/WebSocket → Data Pipeline → Feature Calculation
                                ↓
                        Motion Detection → Alerts
                                ↓
                        Database (SQLite) ← Outcome Labeling
                                ↓
                        ML Training ← Hit Rate Analysis
```

## Project Structure

```
Quant/
├── config.yaml                 # Configuration file
├── requirements.txt            # Python dependencies
├── main.py                     # Main system orchestrator
│
├── database/
│   ├── models.py              # SQLAlchemy models
│   └── db_manager.py          # Database operations
│
├── data_pipeline/
│   ├── pumpfun_api.py         # REST API client
│   └── websocket_monitor.py   # WebSocket real-time data
│
├── features/
│   ├── feature_calculator.py  # Real-time feature calculation
│   └── wallet_analyzer.py     # Wallet intelligence tracking
│
├── alerts/
│   └── motion_detector.py     # Motion alert logic
│
├── labeling/
│   └── outcome_labeler.py     # Future outcome labeling
│
├── analysis/
│   └── hit_rate_analyzer.py   # Performance analysis
│
├── ml/
│   ├── model.py               # Neural network architectures
│   └── train.py               # Training script
│
├── scripts/
│   ├── analyze_alerts.py      # Analyze performance
│   ├── train_model.py         # Train ML model
│   └── label_alerts.py        # Label unlabeled alerts
│
├── data/                       # SQLite database (created automatically)
├── logs/                       # Log files (created automatically)
└── models/                     # Trained models (created automatically)
```

## Setup Instructions

### 1. Install Python

Ensure you have Python 3.9+ installed:

```bash
python --version
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

Dependencies include:
- `requests` - API calls
- `websockets` - Real-time data
- `sqlalchemy` - Database ORM
- `pandas` - Data analysis
- `torch` - Machine learning
- `loguru` - Logging

### 3. Configure the System

Edit `config.yaml` to customize thresholds:

```yaml
motion_alert:
  min_buy_volume_sol: 10.0       # Minimum SOL volume
  min_unique_buyers: 30          # Minimum unique buyers
  min_buy_sell_ratio: 2.5        # Buy/sell ratio
  min_txn_velocity: 15           # Transactions per minute
  min_known_wallets: 3           # Known profitable wallets
  max_market_cap: 100000         # Maximum market cap
  max_bonding_curve_pct: 60      # Maximum bonding curve %
```

### 4. Initialize Database

The database will be created automatically when you first run the system:

```bash
python main.py
```

This creates `data/pumpfun_alerts.db` with all necessary tables.

## Usage

### Running the Main System

**Start real-time monitoring:**

```bash
python main.py
```

This will:
1. Connect to Pump.fun WebSocket
2. Monitor new token launches
3. Track all trades in real-time
4. Calculate features for each token
5. Trigger motion alerts when criteria met
6. Label alerts with future outcomes (background task)
7. Update wallet intelligence (background task)

**Stop with:** `Ctrl+C`

### Manual Alert Labeling

Label unlabeled alerts with future performance:

```bash
python scripts/label_alerts.py
```

This queries Pump.fun API to get future prices and labels each alert with:
- Price at 1m, 5m, 15m, 30m, 60m later
- Maximum price reached in 1 hour
- Boolean labels (pumped 10%, 25%, 50%)
- Time to peak

### Analyze Performance

View hit rate statistics:

```bash
python scripts/analyze_alerts.py
```

Output includes:
- Total alerts analyzed
- Hit rates (10%, 25%, 50% thresholds)
- Average returns per timeframe
- Best/worst performers
- Graduation rate
- CSV export for further analysis

### Train ML Model

Once you have 50+ labeled alerts:

```bash
python scripts/train_model.py
```

This will:
1. Load labeled alerts from database
2. Extract features and labels
3. Train a deep neural network
4. Validate on held-out data
5. Save best model to `models/best_model.pt`

The model predicts:
- **Pump probability**: Likelihood of 25%+ gain in 15 minutes
- **Expected return**: Predicted max return in 30 minutes
- **Confidence**: Model confidence in prediction

## Configuration Reference

### Motion Alert Thresholds

Located in `config.yaml` under `motion_alert`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `min_buy_volume_sol` | 10.0 | Minimum SOL buy volume in time window |
| `min_unique_buyers` | 30 | Minimum unique buyer wallets |
| `min_buy_sell_ratio` | 2.5 | Minimum ratio of buys to sells |
| `min_txn_velocity` | 15 | Minimum transactions per minute |
| `min_known_wallets` | 3 | Minimum known profitable wallets participating |
| `max_market_cap` | 100000 | Maximum market cap in USD |
| `max_bonding_curve_pct` | 60 | Maximum bonding curve completion % |
| `min_time_since_launch` | 60 | Minimum seconds since launch (avoid bot spam) |

### Wallet Intelligence

Located under `wallet_intelligence`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `min_trades` | 5 | Minimum trades to evaluate wallet |
| `min_win_rate` | 0.40 | Minimum 40% win rate |
| `min_total_pnl_sol` | 5.0 | Minimum 5 SOL total profit |
| `lookback_days` | 30 | Days of history to analyze |

### Labeling Configuration

Located under `labeling`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `future_intervals` | [1, 5, 15, 30, 60] | Minutes to check future prices |
| `pump_thresholds.small` | 0.10 | 10% pump threshold |
| `pump_thresholds.medium` | 0.25 | 25% pump threshold |
| `pump_thresholds.large` | 0.50 | 50% pump threshold |

## Workflow

### Phase 1: Data Collection (Week 1-2)

1. **Start monitoring:**
   ```bash
   python main.py
   ```

2. **Let it run continuously** to collect token launches, trades, and alerts

3. **Target**: Collect 100-500 alerts

### Phase 2: Analysis (Week 3)

1. **Label alerts:**
   ```bash
   python scripts/label_alerts.py
   ```

2. **Analyze performance:**
   ```bash
   python scripts/analyze_alerts.py
   ```

3. **Optimize thresholds** in `config.yaml` based on hit rates

### Phase 3: ML Training (Week 4+)

1. **Train initial model:**
   ```bash
   python scripts/train_model.py
   ```

2. **Evaluate** model predictions vs rule-based alerts

3. **Iterate** on features and model architecture

### Phase 4: Production

1. **Integrate ML predictions** into alert system
2. **A/B test** rule-based vs ML-enhanced alerts
3. **Continuously retrain** as more data accumulates

## Understanding Alerts

When a motion alert triggers, you'll see:

```
╔══════════════════════════════════════╗
║       MOTION ALERT TRIGGERED         ║
╚══════════════════════════════════════╝

Token: PUMP (PumpCoin)
Mint: 7xKXt...

📊 Entry Metrics:
   Market Cap: $45,230
   Price: 0.00012500 SOL
   Bonding Curve: 35.2%

📈 3-Minute Activity:
   Buy Volume: 12.50 SOL
   Unique Buyers: 45
   Buy/Sell Ratio: 3.8
   Txn Velocity: 18.2/min

👛 Smart Money:
   Known Wallets: 5
   Known %: 11.1%

⏰ Time Since Launch: 120s
```

This indicates:
- **Strong momentum** (high buy volume, many buyers)
- **Positive sentiment** (more buys than sells)
- **Smart money interest** (known profitable wallets buying)
- **Early entry** (low market cap, low bonding curve %)

## Database Schema

### Core Tables

- **token_launches**: All Pump.fun token launches
- **transactions**: Individual buy/sell trades
- **token_snapshots**: Time-series price/market cap data
- **motion_alerts**: Triggered alerts with features and outcomes
- **wallet_intelligence**: Wallet profitability tracking

All data stored locally in `data/pumpfun_alerts.db` (SQLite).

## Performance Metrics

### What to Track

1. **Hit Rate**: % of alerts that pump by threshold (target: >30% for 25%+ gain)
2. **Average Return**: Mean max return after alert (target: >50%)
3. **Time to Peak**: How long until max price (target: <15 min)
4. **False Positive Rate**: % of alerts that dump (target: <40%)
5. **Graduation Rate**: % that graduate to Raydium (signal of legitimacy)

### Optimization

- **Too many alerts**: Increase thresholds (volume, buyers, etc.)
- **Too few alerts**: Decrease thresholds
- **Low hit rate**: Adjust `min_known_wallets` or `buy_sell_ratio`
- **Late entries**: Decrease `max_bonding_curve_pct` or `max_market_cap`

## Troubleshooting

### WebSocket Connection Issues

If WebSocket disconnects frequently:
1. Check internet connection
2. Pump.fun API may be rate limiting
3. System will auto-reconnect with exponential backoff

### No Alerts Triggering

Possible causes:
1. **Thresholds too strict**: Lower values in `config.yaml`
2. **No known wallets**: Run longer to build wallet intelligence
3. **Market conditions**: Low activity period on Pump.fun

### Database Locked Errors

SQLite limitations with concurrent writes:
1. Ensure only one instance of `main.py` running
2. Consider upgrading to PostgreSQL for production

### Import Errors

Make sure all dependencies installed:
```bash
pip install -r requirements.txt --upgrade
```

## Advanced Usage

### Custom Alert Actions

Edit `main.py` → `handle_alert()` method to add custom actions:

```python
def handle_alert(self, alert_data: dict):
    # Print summary
    summary = self.motion_detector.get_alert_summary(alert_data)
    logger.info(f"\n{summary}\n")

    # Add your custom action:
    # - Send Discord notification
    # - Execute trade via Solana wallet
    # - Log to external service
    # etc.
```

### Filtering Tokens

To only monitor specific types of tokens, edit `handle_new_token()`:

```python
async def handle_new_token(self, token_data: dict):
    # Skip NSFW tokens
    if token_data.get('metadata', {}).get('nsfw', False):
        return

    # Skip tokens without social links
    metadata = token_data.get('metadata', {})
    if not metadata.get('twitter') and not metadata.get('telegram'):
        return

    # Continue processing...
```

### Export Data

Export alerts to CSV for Excel/Python analysis:

```python
from analysis.hit_rate_analyzer import HitRateAnalyzer
analyzer = HitRateAnalyzer(db)
analyzer.export_to_csv("my_alerts.csv")
```

## Future Enhancements

Potential additions:
- [ ] Social sentiment analysis (Twitter, Telegram)
- [ ] Image/metadata analysis for rug detection
- [ ] Multi-DEX support (Raydium, Jupiter)
- [ ] Live dashboard (Streamlit/Grafana)
- [ ] Automated trading execution
- [ ] Discord/Telegram bot notifications
- [ ] Cloud database (PostgreSQL/TimescaleDB)
- [ ] Backtesting framework
- [ ] Portfolio tracking

## Security Notes

- **Never commit API keys** to git
- **Use paper trading first** before real funds
- **This is experimental software** - use at your own risk
- **Memecoin trading is extremely risky** - most tokens go to zero

## License

This project is for educational purposes. Use responsibly.

## Support

For issues or questions, consult:
- Pump.fun documentation
- Solana Web3 documentation
- PyTorch documentation

---

**Happy trading! 🚀**
#   p u m p f u n - m o t i o n - a l e r t s 
 
 