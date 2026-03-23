"""
Data validation service for OHLCV candle data
"""
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

@dataclass
class ValidationIssue:
    """Represents a validation issue"""
    timestamp: str
    row_index: int
    issue_type: str
    severity: str  # "error", "warning", "info"
    description: str

@dataclass
class DataValidationReport:
    """Data validation report"""
    symbol: str
    total_candles: int
    date_range: Dict
    issues: List[Dict]
    warnings: List[Dict]
    statistics: Dict
    validation_status: str  # "ok", "warning", "error"

class OHLCVValidator:
    """OHLCV candle data validator"""
    
    def __init__(self):
        self.df = None
        self.issues = []
        self.warnings = []
    
    def load_from_dataframe(self, df: pd.DataFrame):
        """Load data from pandas DataFrame"""
        self.df = df.copy()
        self.df['Date'] = pd.to_datetime(self.df['Date'])
        self.df = self.df.sort_values('Date').reset_index(drop=True)
        logger.info(f"Loaded {len(self.df)} rows from DataFrame")
    
    def validate_ohlc_relationships(self) -> Dict:
        """Validate OHLC candle relationships"""
        logger.info("Validating OHLC relationships...")
        
        issues = []
        for idx, row in self.df.iterrows():
            # High >= Low
            if row['High'] < row['Low']:
                issues.append(ValidationIssue(
                    timestamp=str(row['Date']),
                    row_index=idx,
                    issue_type="ohlc_high_low",
                    severity="error",
                    description=f"High ({row['High']:.2f}) < Low ({row['Low']:.2f})"
                ))
            
            # High >= Open, Close
            if row['High'] < row['Open'] or row['High'] < row['Close']:
                issues.append(ValidationIssue(
                    timestamp=str(row['Date']),
                    row_index=idx,
                    issue_type="ohlc_high",
                    severity="error",
                    description=f"High ({row['High']:.2f}) < Open ({row['Open']:.2f}) or Close ({row['Close']:.2f})"
                ))
            
            # Low <= Open, Close
            if row['Low'] > row['Open'] or row['Low'] > row['Close']:
                issues.append(ValidationIssue(
                    timestamp=str(row['Date']),
                    row_index=idx,
                    issue_type="ohlc_low",
                    severity="error",
                    description=f"Low ({row['Low']:.2f}) > Open ({row['Open']:.2f}) or Close ({row['Close']:.2f})"
                ))
            
            # Prices > 0
            if row['Open'] <= 0 or row['High'] <= 0 or row['Low'] <= 0 or row['Close'] <= 0:
                issues.append(ValidationIssue(
                    timestamp=str(row['Date']),
                    row_index=idx,
                    issue_type="negative_price",
                    severity="error",
                    description="Price must be > 0"
                ))
        
        logger.info(f"Found {len(issues)} OHLC validation issues")
        self.issues.extend(issues)
        
        return {
            "total_issues": len(issues),
            "valid": len(issues) == 0,
            "issues": [asdict(i) for i in issues[:5]]  # First 5
        }
    
    def validate_volume(self) -> Dict:
        """Validate volume data"""
        logger.info("Validating volume...")
        
        issues = []
        
        # Volume > 0
        zero_vol = self.df[self.df['Volume'] <= 0]
        for idx, row in zero_vol.iterrows():
            issues.append(ValidationIssue(
                timestamp=str(row['Date']),
                row_index=idx,
                issue_type="zero_volume",
                severity="warning",
                description=f"Volume is {row['Volume']}, expected > 0"
            ))
        
        # Volume outliers (>3σ)
        if len(self.df) > 1:
            vol_mean = self.df['Volume'].mean()
            vol_std = self.df['Volume'].std()
            
            outliers = self.df[self.df['Volume'] > vol_mean + 3 * vol_std]
            for idx, row in outliers.iterrows():
                self.warnings.append(ValidationIssue(
                    timestamp=str(row['Date']),
                    row_index=idx,
                    issue_type="volume_outlier",
                    severity="warning",
                    description=f"Volume {int(row['Volume'])} is >3σ from mean"
                ))
        
        logger.info(f"Found {len(issues)} volume issues, {len(self.warnings)} outliers")
        self.issues.extend(issues)
        
        return {
            "zero_volume": len(issues),
            "outlier_count": len(self.warnings),
            "valid": len(issues) == 0
        }
    
    def detect_gaps(self, min_gap_days: int = 5) -> Dict:
        """Detect date gaps in trading data"""
        logger.info(f"Detecting gaps > {min_gap_days} days...")
        
        gaps = []
        
        df_sorted = self.df.sort_values('Date')
        
        for i in range(1, len(df_sorted)):
            prev_date = df_sorted.iloc[i-1]['Date']
            curr_date = df_sorted.iloc[i]['Date']
            
            gap_days = (curr_date - prev_date).days
            
            if gap_days > min_gap_days:
                gaps.append({
                    "start": str(prev_date.date()),
                    "end": str(curr_date.date()),
                    "days": gap_days
                })
                
                self.warnings.append(ValidationIssue(
                    timestamp=str(curr_date),
                    row_index=i,
                    issue_type="date_gap",
                    severity="warning",
                    description=f"Gap of {gap_days} days"
                ))
        
        logger.info(f"Found {len(gaps)} gaps")
        
        return {
            "gap_count": len(gaps),
            "gaps": gaps[:5],
            "has_gaps": len(gaps) > 0
        }
    
    def detect_outliers(self, z_threshold: float = 3.0) -> Dict:
        """Detect price outliers using Z-score"""
        logger.info(f"Detecting outliers (Z > {z_threshold})...")
        
        outliers = []
        
        if len(self.df) < 2:
            return {"outlier_count": 0, "outliers": []}
        
        # Calculate daily returns
        df_sorted = self.df.sort_values('Date').reset_index(drop=True)
        df_sorted['Returns'] = df_sorted['Close'].pct_change()
        
        # Find outliers using Z-score
        returns = df_sorted['Returns'].dropna()
        returns_mean = returns.mean()
        returns_std = returns.std()
        
        for idx, row in df_sorted.iterrows():
            if idx == 0:
                continue
            
            if returns_std > 0:
                zscore = abs((row['Returns'] - returns_mean) / returns_std)
            else:
                zscore = 0
            
            if zscore > z_threshold:
                outliers.append({
                    "date": str(row['Date'].date()),
                    "return": float(row['Returns'] * 100),
                    "zscore": float(zscore),
                    "price": float(row['Close'])
                })
                
                self.warnings.append(ValidationIssue(
                    timestamp=str(row['Date']),
                    row_index=idx,
                    issue_type="price_outlier",
                    severity="warning",
                    description=f"Return {row['Returns']*100:.2f}% (Z: {zscore:.2f})"
                ))
        
        logger.info(f"Found {len(outliers)} price outliers")
        
        return {
            "outlier_count": len(outliers),
            "outliers": outliers[:5],
            "has_outliers": len(outliers) > 0
        }
    
    def get_statistics(self) -> Dict:
        """Calculate data statistics"""
        logger.info("Calculating statistics...")
        
        if self.df is None or self.df.empty:
            return {}
        
        return {
            "total_rows": len(self.df),
            "date_range": {
                "start": str(self.df['Date'].min().date()),
                "end": str(self.df['Date'].max().date()),
            },
            "symbols": self.df['Symbol'].unique().tolist() if 'Symbol' in self.df else [],
            "price_stats": {
                "open": {
                    "min": float(self.df['Open'].min()),
                    "max": float(self.df['Open'].max()),
                    "mean": float(self.df['Open'].mean()),
                },
                "close": {
                    "min": float(self.df['Close'].min()),
                    "max": float(self.df['Close'].max()),
                    "mean": float(self.df['Close'].mean()),
                },
                "high": {
                    "min": float(self.df['High'].min()),
                    "max": float(self.df['High'].max()),
                },
                "low": {
                    "min": float(self.df['Low'].min()),
                    "max": float(self.df['Low'].max()),
                }
            },
            "volume_stats": {
                "min": int(self.df['Volume'].min()),
                "max": int(self.df['Volume'].max()),
                "mean": int(self.df['Volume'].mean()),
            }
        }
    
    def run_full_validation(self) -> DataValidationReport:
        """Run complete validation"""
        logger.info("\n" + "="*60)
        logger.info("RUNNING FULL OHLCV VALIDATION")
        logger.info("="*60)
        
        if self.df is None or self.df.empty:
            return DataValidationReport(
                symbol="UNKNOWN",
                total_candles=0,
                date_range={},
                issues=[],
                warnings=[],
                statistics={},
                validation_status="error"
            )
        
        # Run all validations
        ohlc_result = self.validate_ohlc_relationships()
        volume_result = self.validate_volume()
        gaps_result = self.detect_gaps()
        outliers_result = self.detect_outliers()
        
        stats = self.get_statistics()
        
        # Determine overall status
        if len(self.issues) > 0:
            validation_status = "error"
        elif len(self.warnings) > 0:
            validation_status = "warning"
        else:
            validation_status = "ok"
        
        report = DataValidationReport(
            symbol=self.df['Symbol'].iloc[0] if 'Symbol' in self.df else "UNKNOWN",
            total_candles=len(self.df),
            date_range={
                "start": str(self.df['Date'].min().date()),
                "end": str(self.df['Date'].max().date())
            },
            issues=[asdict(i) for i in self.issues],
            warnings=[asdict(w) for w in self.warnings],
            statistics=stats,
            validation_status=validation_status
        )
        
        # Log summary
        logger.info("\n" + "="*60)
        logger.info("VALIDATION REPORT")
        logger.info("="*60)
        logger.info(f"Symbol: {report.symbol}")
        logger.info(f"Total Candles: {report.total_candles}")
        logger.info(f"Date Range: {report.date_range['start']} to {report.date_range['end']}")
        logger.info(f"Validation Issues: {len(report.issues)}")
        logger.info(f"Warnings: {len(report.warnings)}")
        logger.info(f"Status: {report.validation_status.upper()}")
        logger.info("="*60 + "\n")
        
        return report
