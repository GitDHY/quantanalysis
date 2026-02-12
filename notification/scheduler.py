"""
Alert scheduler module for periodic strategy checks.
Supports automatic subscription-based strategy monitoring.
"""

import json
import threading
import time
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List
from dataclasses import dataclass

from config.settings import get_settings, NotificationSubscription


@dataclass
class ScheduleConfig:
    """Scheduler configuration."""
    enabled: bool = False
    frequency: str = "daily"  # daily, weekly
    check_time: str = "09:30"
    last_run: str = ""
    
    def should_run_now(self) -> bool:
        """Check if scheduler should run based on current time."""
        if not self.enabled:
            return False
        
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        today = now.strftime("%Y-%m-%d")
        
        # Check if already run today
        if self.last_run == today:
            return False
        
        # Check if it's time to run
        if current_time >= self.check_time:
            return True
        
        return False


@dataclass  
class CheckResult:
    """Result of a single subscription check."""
    subscription_id: str
    strategy_name: str
    portfolio_name: str
    success: bool
    has_changes: bool
    changes_count: int
    email_sent: bool
    wechat_sent: bool
    error: str = ""
    signals: List[str] = None
    
    def __post_init__(self):
        if self.signals is None:
            self.signals = []


class AlertScheduler:
    """
    Scheduler for periodic strategy alert checks.
    Runs in background thread and triggers strategy evaluation.
    """
    
    def __init__(self):
        """Initialize scheduler."""
        self.settings = get_settings()
        self.config_file = self.settings.base_dir / "data" / "scheduler_config.json"
        self.lock_file = self.settings.base_dir / "data" / "scheduler.lock"
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._check_callbacks: List[Callable] = []
        
        # Ensure data directory exists
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
    
    def load_config(self) -> ScheduleConfig:
        """Load scheduler configuration."""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                return ScheduleConfig(
                    enabled=data.get('enabled', False),
                    frequency=data.get('frequency', 'daily'),
                    check_time=data.get('check_time', '09:30'),
                    last_run=data.get('last_run', ''),
                )
            except Exception:
                pass
        return ScheduleConfig()
    
    def save_config(self, config: ScheduleConfig) -> bool:
        """Save scheduler configuration."""
        try:
            data = {
                'enabled': config.enabled,
                'frequency': config.frequency,
                'check_time': config.check_time,
                'last_run': config.last_run,
            }
            with open(self.config_file, 'w') as f:
                json.dump(data, f, indent=4)
            return True
        except Exception:
            return False
    
    def update_last_run(self):
        """Update last run timestamp."""
        config = self.load_config()
        config.last_run = datetime.now().strftime("%Y-%m-%d")
        self.save_config(config)
    
    def add_check_callback(self, callback: Callable):
        """
        Add a callback function to be called during scheduled checks.
        
        Args:
            callback: Function to call (should return Dict with results)
        """
        self._check_callbacks.append(callback)
    
    def remove_check_callback(self, callback: Callable):
        """Remove a callback function."""
        if callback in self._check_callbacks:
            self._check_callbacks.remove(callback)
    
    def _acquire_lock(self) -> bool:
        """Acquire scheduler lock to prevent multiple instances."""
        try:
            if self.lock_file.exists():
                # Check if lock is stale (older than 1 hour)
                mtime = datetime.fromtimestamp(self.lock_file.stat().st_mtime)
                if (datetime.now() - mtime).total_seconds() > 3600:
                    self.lock_file.unlink()
                else:
                    return False
            
            self.lock_file.write_text(str(datetime.now()))
            return True
        except Exception:
            return False
    
    def _release_lock(self):
        """Release scheduler lock."""
        try:
            if self.lock_file.exists():
                self.lock_file.unlink()
        except Exception:
            pass
    
    def _run_checks(self) -> Dict[str, Any]:
        """
        Run all registered check callbacks.
        
        Returns:
            Dictionary with results from all callbacks
        """
        results = {
            'timestamp': datetime.now().isoformat(),
            'checks': [],
        }
        
        for callback in self._check_callbacks:
            try:
                result = callback()
                results['checks'].append({
                    'callback': callback.__name__,
                    'success': True,
                    'result': result,
                })
            except Exception as e:
                results['checks'].append({
                    'callback': callback.__name__,
                    'success': False,
                    'error': str(e),
                })
        
        return results
    
    def _scheduler_loop(self):
        """Main scheduler loop running in background thread."""
        while self._running:
            try:
                config = self.load_config()
                
                if config.should_run_now():
                    # Run subscription checks
                    results = self.run_subscription_checks()
                    
                    # Also run any custom callbacks
                    callback_results = self._run_checks()
                    
                    # Update last run
                    self.update_last_run()
                    
                    # Log results
                    print(f"Scheduler ran at {datetime.now().isoformat()}")
                    print(f"  Subscriptions checked: {len(results)}")
                    print(f"  With changes: {sum(1 for r in results if r.has_changes)}")
                
            except Exception as e:
                print(f"Scheduler error: {e}")
            
            # Sleep for 60 seconds before next check
            for _ in range(60):
                if not self._running:
                    break
                time.sleep(1)
    
    def start(self) -> bool:
        """
        Start the scheduler background thread.
        
        Returns:
            True if started successfully
        """
        if self._running:
            return True
        
        if not self._acquire_lock():
            return False
        
        self._running = True
        self._thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._thread.start()
        
        return True
    
    def stop(self):
        """Stop the scheduler background thread."""
        self._running = False
        self._release_lock()
        
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
    
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._running
    
    def run_now(self) -> Dict[str, Any]:
        """
        Manually trigger a check run immediately.
        
        Returns:
            Results dictionary
        """
        return self._run_checks()
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current scheduler status.
        
        Returns:
            Status dictionary
        """
        config = self.load_config()
        
        return {
            'enabled': config.enabled,
            'running': self._running,
            'frequency': config.frequency,
            'check_time': config.check_time,
            'last_run': config.last_run,
            'callbacks_count': len(self._check_callbacks),
        }
    
    def run_subscription_checks(self) -> List[CheckResult]:
        """
        Run all enabled subscription checks.
        This is the main method for scheduled strategy checks.
        
        Returns:
            List of CheckResult for each subscription
        """
        from strategy.engine import StrategyEngine
        from portfolio.manager import PortfolioManager
        from notification.email_sender import EmailSender
        from notification.wechat_push import WeChatPush
        
        results: List[CheckResult] = []
        
        # Load notification config with subscriptions
        notification_config = self.settings.load_notification_config()
        
        # Filter to only enabled subscriptions
        active_subs = [s for s in notification_config.subscriptions if s.enabled]
        
        if not active_subs:
            return results
        
        # Initialize engines
        strategy_engine = StrategyEngine()
        portfolio_manager = PortfolioManager()
        email_sender = EmailSender(notification_config)
        wechat_push = WeChatPush(notification_config)
        
        for sub in active_subs:
            result = self._check_single_subscription(
                sub,
                strategy_engine,
                portfolio_manager,
                email_sender,
                wechat_push,
                notification_config,
            )
            results.append(result)
        
        return results
    
    def _check_single_subscription(
        self,
        subscription: NotificationSubscription,
        strategy_engine,
        portfolio_manager,
        email_sender,
        wechat_push,
        notification_config,
    ) -> CheckResult:
        """
        Check a single subscription and send notifications if needed.
        
        Args:
            subscription: The subscription to check
            strategy_engine: StrategyEngine instance
            portfolio_manager: PortfolioManager instance
            email_sender: EmailSender instance
            wechat_push: WeChatPush instance
            notification_config: NotificationDefaults config
            
        Returns:
            CheckResult with the outcome
        """
        result = CheckResult(
            subscription_id=subscription.id,
            strategy_name=subscription.strategy_name,
            portfolio_name=subscription.portfolio_name,
            success=False,
            has_changes=False,
            changes_count=0,
            email_sent=False,
            wechat_sent=False,
        )
        
        try:
            # Get strategy and portfolio
            strategy = strategy_engine.get(subscription.strategy_name)
            portfolio = portfolio_manager.get(subscription.portfolio_name)
            
            if not strategy:
                result.error = f"Strategy '{subscription.strategy_name}' not found"
                return result
            
            if not portfolio:
                result.error = f"Portfolio '{subscription.portfolio_name}' not found"
                return result
            
            # Execute strategy
            exec_result = strategy_engine.execute(
                code=strategy['code'],
                tickers=portfolio.tickers,
                current_weights=portfolio.weights,
            )
            
            if not exec_result.success:
                result.error = exec_result.message
                return result
            
            result.success = True
            result.signals = exec_result.signals
            
            # Check for significant changes
            changes = []
            current_weights = portfolio.weights
            target_weights = exec_result.target_weights
            
            for ticker in set(list(current_weights.keys()) + list(target_weights.keys())):
                current = current_weights.get(ticker, 0)
                target = target_weights.get(ticker, 0)
                change = abs(target - current)
                
                if change >= subscription.threshold_pct:
                    changes.append(ticker)
            
            result.changes_count = len(changes)
            result.has_changes = len(changes) > 0
            
            # Send notifications if there are changes
            if result.has_changes:
                reason = "\n".join(exec_result.signals[:5]) if exec_result.signals else "策略信号触发"
                
                # Send email
                if subscription.notify_email and email_sender.is_configured():
                    email_result = email_sender.send_strategy_alert(
                        strategy_name=subscription.strategy_name,
                        current_weights=current_weights,
                        target_weights=target_weights,
                        reason=reason,
                    )
                    result.email_sent = email_result.success
                
                # Send WeChat
                if subscription.notify_wechat and wechat_push.is_configured():
                    wechat_result = wechat_push.send_strategy_alert(
                        strategy_name=subscription.strategy_name,
                        current_weights=current_weights,
                        target_weights=target_weights,
                        reason=reason,
                    )
                    result.wechat_sent = wechat_result.success
            
            return result
            
        except Exception as e:
            result.error = str(e)
            return result
