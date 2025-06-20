#!/usr/bin/env python3
import json
import time
import os
from datetime import datetime, timedelta
from collections import deque
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class HistoricalPriceTracker:
    def __init__(self, json_file_path="data/equipment_prices.json", 
                 history_dir="data/price_history"):
        self.json_file_path = json_file_path
        self.history_dir = history_dir
        
        # ディレクトリ作成
        os.makedirs(history_dir, exist_ok=True)
        
        # 修正された時間間隔とデータ保持期間
        self.price_intervals = {
            '1hour': {
                'interval': timedelta(hours=1),
                'maxlen': 168,  # 1週間分（168時間）
                'description': '1週間分（1時間毎）'
            },
            '12hour': {
                'interval': timedelta(hours=12),
                'maxlen': 60,   # 1ヶ月分（60回 = 30日）
                'description': '1ヶ月分（12時間毎）'
            },
            '1day': {
                'interval': timedelta(days=1),
                'maxlen': 365,  # 1年分（365日）
                'description': '1年分（1日毎）'
            }
        }
        
        # 各アイテムの価格履歴を管理するディクショナリ（個別アイテムのみ）
        self.price_history = {}
        
        self.load_existing_history()

    def load_existing_history(self):
        """既存の価格履歴を読み込み（個別アイテムのみ）"""
        try:
            total_records = 0
            for interval_type in self.price_intervals:
                history_file = os.path.join(self.history_dir, f"history_{interval_type}.json")
                if os.path.exists(history_file):
                    with open(history_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        item_count = len(data)
                        for item_id, history in data.items():
                            if item_id not in self.price_history:
                                self.price_history[item_id] = {}
                            
                            # dequeに変換して最大長を適用
                            self.price_history[item_id][interval_type] = deque(
                                history, 
                                maxlen=self.price_intervals[interval_type]['maxlen']
                            )
                            total_records += len(history)
                        logger.info(f"{interval_type} 履歴ファイル読み込み: {item_count}アイテム")
            
            logger.info(f"個別アイテム価格履歴読み込み完了: {len(self.price_history)}アイテム、{total_records}レコード")
        except Exception as e:
            logger.error(f"価格履歴読み込みエラー: {e}")

    def save_history_to_files(self):
        """価格履歴を間隔別ファイルに保存（個別アイテムのみ）"""
        try:
            for interval_type in self.price_intervals:
                history_file = os.path.join(self.history_dir, f"history_{interval_type}.json")
                
                # dequeをリストに変換して保存
                interval_data = {}
                for item_id, intervals in self.price_history.items():
                    if interval_type in intervals and len(intervals[interval_type]) > 0:
                        interval_data[item_id] = list(intervals[interval_type])
                
                with open(history_file, 'w', encoding='utf-8') as f:
                    json.dump(interval_data, f, ensure_ascii=False, indent=2)
                
                logger.info(f"{interval_type} 個別履歴保存完了: {len(interval_data)}アイテム")
        except Exception as e:
            logger.error(f"価格履歴保存エラー: {e}")

    def should_update_interval(self, item_id, interval_type):
        """指定した間隔での更新が必要かチェック"""
        if item_id not in self.price_history:
            return True
        
        if interval_type not in self.price_history[item_id]:
            return True
        
        history = self.price_history[item_id][interval_type]
        if not history:
            return True
        
        last_entry = history[-1]
        last_time = datetime.fromisoformat(last_entry['timestamp'].replace('Z', '+00:00'))
        now = datetime.now()
        
        required_interval = self.price_intervals[interval_type]['interval']
        return now - last_time >= required_interval

    def update_price_history(self, item_id, item_name, current_price):
        """価格履歴を更新（個別アイテムのみ）"""
        timestamp = datetime.now().isoformat()
        price_point = {
            'timestamp': timestamp,
            'price': current_price,
            'item_name': item_name
        }
        
        # アイテム初期化
        if item_id not in self.price_history:
            self.price_history[item_id] = {}
        
        # 各間隔での更新判定と追加
        updated_intervals = []
        for interval_type, config in self.price_intervals.items():
            if self.should_update_interval(item_id, interval_type):
                if interval_type not in self.price_history[item_id]:
                    self.price_history[item_id][interval_type] = deque(maxlen=config['maxlen'])
                
                self.price_history[item_id][interval_type].append(price_point)
                updated_intervals.append(interval_type)
        
        if updated_intervals:
            logger.info(f"{item_name} 価格履歴更新: {updated_intervals}")
        
        return updated_intervals

    def update_from_current_prices(self):
        """現在の価格JSONから履歴を更新（個別アイテムのみ）"""
        try:
            if not os.path.exists(self.json_file_path):
                logger.error(f"価格ファイルが見つかりません: {self.json_file_path}")
                return 0
            
            with open(self.json_file_path, 'r', encoding='utf-8') as f:
                current_data = json.load(f)
            
            logger.info(f"現在の価格データ読み込み: {len(current_data)}アイテム")
            
            updated_count = 0
            processed_count = 0
            
            for item_id, item_data in current_data.items():
                processed_count += 1
                
                # データ検証
                if not item_data or not isinstance(item_data, dict):
                    continue
                    
                if not item_data.get('item_name') or not item_data.get('item_price'):
                    continue
                
                # 価格文字列を数値に変換
                price_str = str(item_data['item_price']).replace(',', '').replace(' NESO', '').strip()
                try:
                    current_price = int(price_str)
                    if current_price > 0:
                        intervals = self.update_price_history(
                            item_id, 
                            item_data['item_name'], 
                            current_price
                        )
                        if intervals:
                            updated_count += 1
                except (ValueError, TypeError) as e:
                    logger.debug(f"価格変換エラー ({item_id}): {price_str} -> {e}")
                    continue
            
            logger.info(f"個別アイテム処理完了: 処理{processed_count}件、更新{updated_count}件")
            
            if updated_count > 0:
                self.save_history_to_files()
                logger.info(f"個別価格履歴更新完了: {updated_count}アイテム")
            else:
                logger.info("更新すべき価格変更はありませんでした")
            
            return updated_count
            
        except FileNotFoundError:
            logger.error(f"価格ファイルが見つかりません: {self.json_file_path}")
            return 0
        except json.JSONDecodeError as e:
            logger.error(f"JSONファイル読み込みエラー: {e}")
            return 0
        except Exception as e:
            logger.error(f"価格履歴更新エラー: {e}")
            return 0

    def generate_chart_data(self, item_id, interval='1hour'):
        """Chart.js用のデータを生成（デフォルトは1hour/1週間分）"""
        if item_id not in self.price_history:
            return None
        
        if interval not in self.price_history[item_id]:
            return None
        
        history = list(self.price_history[item_id][interval])
        if not history:
            return None
        
        # 時刻フォーマットを間隔に応じて調整
        def format_time(timestamp_str):
            try:
                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                if interval == '1hour':
                    return timestamp.strftime('%m/%d %H:%M')
                elif interval == '12hour':
                    return timestamp.strftime('%m/%d %H:%M')
                else:  # 1day
                    return timestamp.strftime('%m/%d')
            except:
                return timestamp_str
        
        return {
            'labels': [format_time(point['timestamp']) for point in history],
            'datasets': [{
                'label': f'価格 ({self.price_intervals[interval]["description"]})',
                'data': [point['price'] for point in history],
                'borderColor': '#2c3e50',
                'backgroundColor': 'rgba(44, 62, 80, 0.1)',
                'borderWidth': 2,
                'fill': True,
                'tension': 0.3
            }]
        }

    def export_chart_data_for_web(self, item_id, interval='1hour'):
        """Web用にチャートデータをファイル出力"""
        chart_data = self.generate_chart_data(item_id, interval)
        if not chart_data:
            return False
        
        try:
            chart_file = os.path.join(self.history_dir, f"{item_id}_{interval}.json")
            with open(chart_file, 'w', encoding='utf-8') as f:
                json.dump(chart_data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"チャートデータ出力エラー ({item_id}, {interval}): {e}")
            return False

    def get_statistics(self):
        """履歴統計情報を取得"""
        stats = {
            'total_items': len(self.price_history),
            'intervals': {}
        }
        
        for interval_type, config in self.price_intervals.items():
            item_count = sum(1 for item in self.price_history.values() 
                           if interval_type in item and len(item[interval_type]) > 0)
            total_points = sum(len(item[interval_type]) for item in self.price_history.values() 
                             if interval_type in item)
            
            stats['intervals'][interval_type] = {
                'items_with_data': item_count,
                'total_data_points': total_points,
                'description': config['description'],
                'max_points': config['maxlen']
            }
        
        return stats

def main():
    """メイン実行：現在の価格から履歴を更新（個別アイテムのみ）"""
    logger.info("=" * 50)
    logger.info("MapleStory個別アイテム価格履歴更新開始")
    logger.info("=" * 50)
    
    try:
        # システム初期化
        logger.info("個別アイテム価格追跡システム初期化: data/price_history")
        tracker = HistoricalPriceTracker()
        
        # 現在の価格データから履歴更新
        updated = tracker.update_from_current_prices()
        
        # 統計表示
        stats = tracker.get_statistics()
        logger.info(f"📊 個別アイテム価格履歴統計:")
        logger.info(f"  総アイテム数: {stats['total_items']}")
        for interval, data in stats['intervals'].items():
            logger.info(f"  {interval}: {data['items_with_data']}件 ({data['description']}) - {data['total_data_points']}ポイント")
        
        logger.info("=" * 50)
        logger.info(f"✅ 個別アイテム更新完了: {updated}アイテム")
        logger.info("=" * 50)
        
        return updated
        
    except Exception as e:
        logger.error(f"メイン実行エラー: {e}")
        raise

if __name__ == "__main__":
    main()
