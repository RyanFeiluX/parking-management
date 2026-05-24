import os
import sys
import sqlite3

db_path = 'parking.db'
backup_path = 'parking_backup.db'

if os.path.exists(backup_path):
    os.remove(backup_path)

if os.path.exists(db_path):
    try:
        os.rename(db_path, backup_path)
        print(f"数据库已备份到 {backup_path}")
    except Exception as e:
        print(f"无法备份数据库: {e}")
        print("尝试直接删除...")
        try:
            os.remove(db_path)
            print("数据库已删除")
        except Exception as e2:
            print(f"删除失败: {e2}")
            sys.exit(1)
else:
    print("数据库不存在")

print("完成！")
