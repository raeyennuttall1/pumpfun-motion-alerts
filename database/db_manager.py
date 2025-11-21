"""
Database manager for SQLite operations
"""
import os
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from loguru import logger

from database.models import Base, TokenLaunch, TokenSnapshot, Transaction, MotionAlert, WalletIntelligence


class DatabaseManager:
    """Manages database connections and operations"""

    def __init__(self, db_path: str = "data/pumpfun_alerts.db", echo: bool = False):
        """Initialize database connection"""
        # Ensure data directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        # Create engine
        self.engine = create_engine(f'sqlite:///{db_path}', echo=echo)
        self.SessionLocal = sessionmaker(bind=self.engine)

        # Create tables
        Base.metadata.create_all(self.engine)
        logger.info(f"Database initialized at {db_path}")

    @contextmanager
    def get_session(self) -> Session:
        """Context manager for database sessions"""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()

    # Token Launch Operations
    def add_token_launch(self, token_data: Dict[str, Any]) -> Optional[TokenLaunch]:
        """Add a new token launch"""
        with self.get_session() as session:
            existing = session.query(TokenLaunch).filter_by(
                mint_address=token_data['mint_address']
            ).first()

            if existing:
                logger.debug(f"Token {token_data['mint_address']} already exists")
                return existing

            token = TokenLaunch(**token_data)
            session.add(token)
            logger.info(f"Added new token: {token_data['symbol']} ({token_data['mint_address']})")
            return token

    def get_token(self, mint_address: str) -> Optional[Dict[str, Any]]:
        """Get token by mint address - returns dict to avoid session issues"""
        with self.get_session() as session:
            token = session.query(TokenLaunch).filter_by(mint_address=mint_address).first()
            if token:
                return {
                    'mint_address': token.mint_address,
                    'name': token.name,
                    'symbol': token.symbol,
                    'created_timestamp': token.created_timestamp,
                    'creator_address': token.creator_address
                }
            return None

    def get_recent_launches(self, hours: int = 24, limit: int = 100) -> List[TokenLaunch]:
        """Get recent token launches"""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        with self.get_session() as session:
            return session.query(TokenLaunch).filter(
                TokenLaunch.created_timestamp >= cutoff
            ).order_by(TokenLaunch.created_timestamp.desc()).limit(limit).all()

    # Transaction Operations
    def add_transaction(self, txn_data: Dict[str, Any]) -> Optional[Transaction]:
        """Add a transaction"""
        with self.get_session() as session:
            # Check if exists
            existing = session.query(Transaction).filter_by(
                signature=txn_data['signature']
            ).first()

            if existing:
                return existing

            txn = Transaction(**txn_data)
            session.add(txn)
            return txn

    def get_transactions(
        self,
        mint_address: str,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> List[Transaction]:
        """Get transactions for a token"""
        with self.get_session() as session:
            query = session.query(Transaction).filter_by(mint_address=mint_address)

            if since:
                query = query.filter(Transaction.timestamp >= since)
            if until:
                query = query.filter(Transaction.timestamp <= until)

            query = query.order_by(Transaction.timestamp.desc())

            if limit:
                query = query.limit(limit)

            return query.all()

    # Snapshot Operations
    def add_snapshot(self, snapshot_data: Dict[str, Any]) -> TokenSnapshot:
        """Add a token snapshot"""
        with self.get_session() as session:
            snapshot = TokenSnapshot(**snapshot_data)
            session.add(snapshot)
            return snapshot

    def get_latest_snapshot(self, mint_address: str) -> Optional[Dict[str, Any]]:
        """Get latest snapshot for a token - returns dict to avoid session issues"""
        with self.get_session() as session:
            snapshot = session.query(TokenSnapshot).filter_by(
                mint_address=mint_address
            ).order_by(TokenSnapshot.timestamp.desc()).first()
            if snapshot:
                return {
                    'mint_address': snapshot.mint_address,
                    'timestamp': snapshot.timestamp,
                    'market_cap': snapshot.market_cap,
                    'price_sol': snapshot.price_sol,
                    'bonding_curve_pct': snapshot.bonding_curve_pct,
                    'graduated': snapshot.graduated
                }
            return None

    def get_snapshot_at_time(self, mint_address: str, timestamp: datetime) -> Optional[TokenSnapshot]:
        """Get snapshot closest to a specific time"""
        with self.get_session() as session:
            # Get closest snapshot before or at the timestamp
            return session.query(TokenSnapshot).filter(
                TokenSnapshot.mint_address == mint_address,
                TokenSnapshot.timestamp <= timestamp
            ).order_by(TokenSnapshot.timestamp.desc()).first()

    # Motion Alert Operations
    def add_alert(self, alert_data: Dict[str, Any]) -> MotionAlert:
        """Add a motion alert"""
        with self.get_session() as session:
            alert = MotionAlert(**alert_data)
            session.add(alert)
            logger.info(f"Alert created for {alert_data['mint_address']}")
            return alert

    def get_unlabeled_alerts(self, limit: int = 100) -> List[MotionAlert]:
        """Get alerts that haven't been labeled yet"""
        with self.get_session() as session:
            return session.query(MotionAlert).filter_by(
                labeled=False
            ).order_by(MotionAlert.alert_timestamp).limit(limit).all()

    def update_alert_outcomes(self, alert_id: int, outcomes: Dict[str, Any]) -> bool:
        """Update alert with future outcomes"""
        with self.get_session() as session:
            alert = session.query(MotionAlert).filter_by(alert_id=alert_id).first()
            if not alert:
                return False

            for key, value in outcomes.items():
                setattr(alert, key, value)

            alert.labeled = True
            alert.labeled_at = datetime.utcnow()
            logger.debug(f"Updated outcomes for alert {alert_id}")
            return True

    def get_alerts_for_analysis(self, labeled_only: bool = True) -> List[MotionAlert]:
        """Get alerts for hit rate analysis"""
        with self.get_session() as session:
            query = session.query(MotionAlert)
            if labeled_only:
                query = query.filter_by(labeled=True)
            return query.all()

    # Wallet Intelligence Operations
    def update_wallet_intelligence(self, wallet_data: Dict[str, Any]) -> WalletIntelligence:
        """Update or create wallet intelligence record"""
        with self.get_session() as session:
            wallet = session.query(WalletIntelligence).filter_by(
                wallet_address=wallet_data['wallet_address']
            ).first()

            if wallet:
                # Update existing
                for key, value in wallet_data.items():
                    if key != 'wallet_address':
                        setattr(wallet, key, value)
                wallet.last_updated = datetime.utcnow()
            else:
                # Create new
                wallet = WalletIntelligence(**wallet_data)
                session.add(wallet)

            return wallet

    def get_known_profitable_wallets(self) -> List[str]:
        """Get list of known profitable wallet addresses"""
        with self.get_session() as session:
            wallets = session.query(WalletIntelligence.wallet_address).filter_by(
                is_known_profitable=True
            ).all()
            return [w[0] for w in wallets]

    def get_wallet_intelligence(self, wallet_address: str) -> Optional[WalletIntelligence]:
        """Get wallet intelligence by address"""
        with self.get_session() as session:
            return session.query(WalletIntelligence).filter_by(
                wallet_address=wallet_address
            ).first()

    # Statistics
    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics"""
        with self.get_session() as session:
            return {
                'total_tokens': session.query(func.count(TokenLaunch.mint_address)).scalar(),
                'total_transactions': session.query(func.count(Transaction.signature)).scalar(),
                'total_alerts': session.query(func.count(MotionAlert.alert_id)).scalar(),
                'labeled_alerts': session.query(func.count(MotionAlert.alert_id)).filter_by(labeled=True).scalar(),
                'known_wallets': session.query(func.count(WalletIntelligence.wallet_address)).filter_by(
                    is_known_profitable=True
                ).scalar(),
            }
