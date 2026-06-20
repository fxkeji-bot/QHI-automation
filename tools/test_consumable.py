#!/usr/bin/env python3
"""测试耗材管理器"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from services.consumable_manager import ConsumableManager, Consumable, ConsumableCategory, DEFAULT_CONSUMABLES

manager = ConsumableManager()

# 添加默认耗材
for device_name, consumables in DEFAULT_CONSUMABLES.items():
    for c in consumables:
        consumable = Consumable(
            name=c['name'],
            category=c['category'],
            device_id=device_name,
            brand=c['brand'],
            model=c['model'],
            max_level=c['max_level'],
            current_level=c['max_level'],
            unit_price=c['unit_price'],
        )
        manager.add_consumable(consumable)

print(f'Added consumables: {len(manager.list_consumables())}')
print()

print('=== Consumable List ===')
for c in manager.list_consumables():
    print(f'  {c.name} ({c.brand}) - {c.level_percent}% - {c.unit_price}')

print()
print('=== Low Level Alert ===')
for c in manager.list_consumables()[:3]:
    manager.update_level(c.consumable_id, 15)
low = manager.get_low_consumables()
print(f'Low level consumables: {len(low)}')

print()
print('=== Stats ===')
stats = manager.get_consumption_stats()
print(f'  Total: {stats["total_consumables"]}')
print(f'  Value: {stats["total_value"]}')
print(f'  Low: {stats["low_level_count"]}')

print()
print('=== Purchase Suggestions ===')
suggestions = manager.generate_purchase_suggestion()
for s in suggestions[:3]:
    print(f'  {s["name"]} - Priority:{s["priority"]} - {s["unit_price"]}')
