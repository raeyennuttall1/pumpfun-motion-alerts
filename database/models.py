"""
SQLAlchemy database models for Pump.fun motion alert system
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, JSON, ForeignKey, Text, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class TokenLaunch(Base):
    """Stores information about each token launch on Pump.fun"""
    __tablename__ = 'token_launches'

    mint_address = Column(String(44), primary_key=True)
    name = Column(String(255))
    symbol = Column(String(20))
    description = Column(Text, nullable=True)
    creator_address = Column(String(44))
    created_timestamp = Column(DateTime, default=datetime.utcnow)
    bonding_curve = Column(String(44))
    initial_market_cap = Column(Float, default=0.0)
    token_metadata = Column(JSON, nullable=True)

    # Relationships
    snapshots = relationship("TokenSnapshot", back_populates="token", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="token", cascade="all, delete-orphan")
    alerts = relationship("MotionAlert", back_populates="token", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index('idx_created_timestamp', 'created_timestamp'),
        Index('idx_creator_address', 'creator_address'),
    )


class TokenSnapshot(Base):
    """Time-series snapshots of token state"""
    __tablename__ = 'token_snapshots'

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    mint_address = Column(String(44), ForeignKey('token_launches.mint_address'))
    market_cap = Column(Float)
    price_sol = Column(Float)
    total_supply = Column(Float, nullable=True)
    holder_count = Column(Integer, nullable=True)
    bonding_curve_pct = Column(Float, default=0.0)
    graduated = Column(Boolean, default=False)
    volume_1m = Column(Float, default=0.0)
    volume_5m = Column(Float, default=0.0)

    # Relationship
    token = relationship("TokenLaunch", back_populates="snapshots")

    # Indexes
    __table_args__ = (
        Index('idx_snapshot_time', 'timestamp'),
        Index('idx_snapshot_mint_time', 'mint_address', 'timestamp'),
    )


class Transaction(Base):
    """Individual buy/sell transactions"""
    __tablename__ = 'transactions'

    signature = Column(String(88), primary_key=True)
    mint_address = Column(String(44), ForeignKey('token_launches.mint_address'))
    timestamp = Column(DateTime, default=datetime.utcnow)
    wallet_address = Column(String(44))
    is_buy = Column(Boolean)
    sol_amount = Column(Float)
    token_amount = Column(Float)
    market_cap_at_time = Column(Float, nullable=True)

    # Relationship
    token = relationship("TokenLaunch", back_populates="transactions")

    # Indexes
    __table_args__ = (
        Index('idx_txn_mint_time', 'mint_address', 'timestamp'),
        Index('idx_txn_wallet', 'wallet_address'),
        Index('idx_txn_time', 'timestamp'),
    )


class MotionAlert(Base):
    """Motion alerts with entry metrics and future outcomes"""
    __tablename__ = 'motion_alerts'

    alert_id = Column(Integer, primary_key=True, autoincrement=True)
    mint_address = Column(String(44), ForeignKey('token_launches.mint_address'))
    alert_timestamp = Column(DateTime, default=datetime.utcnow)
    trigger_features = Column(JSON)

    # Entry metrics
    market_cap_at_alert = Column(Float)
    price_at_alert = Column(Float)
    bonding_curve_pct = Column(Float)

    # Future outcomes (labeled after the fact)
    price_1m_later = Column(Float, nullable=True)
    price_5m_later = Column(Float, nullable=True)
    price_15m_later = Column(Float, nullable=True)
    price_30m_later = Column(Float, nullable=True)
    price_60m_later = Column(Float, nullable=True)
    max_price_1h = Column(Float, nullable=True)

    # Labels for ML
    pumped_10pct_5m = Column(Boolean, nullable=True)
    pumped_25pct_15m = Column(Boolean, nullable=True)
    pumped_50pct_30m = Column(Boolean, nullable=True)
    graduated = Column(Boolean, default=False)
    time_to_peak_minutes = Column(Integer, nullable=True)

    # Labeling status
    labeled = Column(Boolean, default=False)
    labeled_at = Column(DateTime, nullable=True)

    # Relationship
    token = relationship("TokenLaunch", back_populates="alerts")

    # Indexes
    __table_args__ = (
        Index('idx_alert_time', 'alert_timestamp'),
        Index('idx_alert_mint', 'mint_address'),
        Index('idx_alert_labeled', 'labeled'),
    )


class WalletIntelligence(Base):
    """Wallet profitability and behavior tracking"""
    __tablename__ = 'wallet_intelligence'

    wallet_address = Column(String(44), primary_key=True)
    total_trades = Column(Integer, default=0)
    win_count = Column(Integer, default=0)
    loss_count = Column(Integer, default=0)
    total_pnl_sol = Column(Float, default=0.0)
    avg_hold_time_minutes = Column(Float, nullable=True)
    is_known_profitable = Column(Boolean, default=False)
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    trade_history = Column(JSON, nullable=True)  # Summary stats

    # Indexes
    __table_args__ = (
        Index('idx_wallet_profitable', 'is_known_profitable'),
        Index('idx_wallet_updated', 'last_updated'),
    )
