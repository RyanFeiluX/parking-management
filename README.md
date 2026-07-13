# 停车费管理系统

小区包月制停车费管理系统 — 一户多车、车辆按序定档收费、三权分立权限管理。

## 技术栈

- **后端:** FastAPI (Python)
- **数据库:** SQLite (单机，无需安装)
- **模板:** Jinja2 + Bootstrap 5
- **认证:** Session-based (itsdangerous)

## 快速开始

### 面向最终用户

#### 方式一：Windows 安装包（推荐）

运行 `installer\ParkManSetup.exe` 一键安装，自动创建开始菜单和桌面快捷方式，自带卸载程序。

**制作安装包：** 需要先安装 [Inno Setup 6](https://jrsoftware.org/isdl.php)，然后双击：
```cmd
build-installer.bat
```

#### 方式二：单文件 exe 便携版

直接双击 `dist\parkman.exe`，无需安装，等待数秒即可在浏览器中自动打开系统。
- 无需安装 Python
- 数据库自动创建在用户数据目录（`%APPDATA%\停车费管理系统\parking.db`）
- 关闭控制台窗口即停止服务

### 面向开发者

#### 第一步：搭建开发环境

首次使用，双击 `dev_setup.bat`，自动完成：
1. 用 Python 3.12 创建虚拟环境 `venv`
2. 从 `requirements.txt` 安装所有依赖

#### 第二步：启动应用
```cmd
双击 start.bat
```
访问 http://127.0.0.1:8080

### 重新打包

修改源码后：
| 命令 | 产物 |
|------|------|
| `build_exe.bat` | `dist\parkman.exe` |
| `build-installer.bat` | `installer\ParkManSetup.exe` |

## 默认登录

| 用户名 | 密码 | 角色 |
|--------|------|------|
| admin | password123 | super_admin |

## 功能模块

| 模块 | 说明 | 权限 |
|------|------|------|
| Dashboard | 首页仪表盘，车辆状态/收费统计 | 所有用户 |
| Residents | 住户管理（房号/业主/电话） | admin+ |
| Vehicles | 车辆管理（一户多车/排序） | admin+ |
| Payments | 包月缴费（包月/包季/包年），金额自动计算 | 所有用户 |
| Fee Tiers | 收费档位配置（版本化管理） | admin+ |
| Discounts | 优惠策略配置（新能源折扣/免费等） | admin+ |
| **Invoices** | **开票管理（抬头/类型/金额，状态流转）** | **所有用户** |
| Stats | 统计报表 | 所有用户 |
| Users | 用户管理（operator/admin/super_admin） | super_admin |
| Settings | 系统设置（宽限期/临时费率/发票抬头预设） | super_admin |
| Logs | 操作日志审计 | super_admin |

## 发票管理

- 每次交费最多关联一个开票条目（`payment_id` UNIQUE 约束）
- 三种状态：**开票等待中** → **开票已完成** / **申请已取消**
- 支持普票/专票（专票可填纳税人识别号）
- 发票抬头可从预设列表选择（系统设置中维护）
- 入口：缴费记录、车辆状态页、住户详情

## 项目结构

```
parking-management/
├── start.bat                  # 启动应用（自动检测 venv）
├── dev_setup.bat              # 一键搭建开发环境（创建 venv + 安装依赖）
├── build_exe.bat              # 打包为单文件 exe
├── build-installer.bat        # 制作 Windows 安装包
├── installer.iss              # Inno Setup 安装脚本
├── run.py                     # Python 入口
├── requirements.txt           # 依赖列表
├── data/                      # 用户数据目录（自动创建，开发模式）
│   ├── parking.db             # SQLite 数据库
│   └── config.json            # 数据库路径配置
├── dist/                      # exe 输出目录
│   └── parkman.exe
├── 启动说明.md
├── 停车费管理系统_规格说明书.md
├── app/
│   ├── __init__.py
│   ├── _path.py               # 路径辅助（资源目录/用户数据目录/配置读写）
│   ├── migration.py            # Schema 迁移框架
│   ├── main.py                # FastAPI 应用
│   ├── jinja.py               # Jinja2 模板引擎
│   ├── models.py              # SQLAlchemy ORM 模型
│   ├── schemas.py             # Pydantic 校验
│   ├── database.py            # DB 引擎 & Session
│   ├── auth.py                # 密码哈希 & Session
│   ├── deps.py                # 依赖注入（权限检查）
│   ├── utils.py               # 业务逻辑
│   ├── routers/               # 路由处理器
│   │   ├── invoices.py
│   │   ├── payments.py
│   │   ├── residents.py
│   │   ├── vehicles.py
│   │   ├── fee_tiers.py
│   │   ├── discounts.py
│   │   ├── users.py
│   │   ├── settings.py
│   │   ├── stats.py
│   │   ├── logs.py
│   │   └── api.py
│   ├── static/
│   │   ├── favicon.svg
│   │   └── js/notification.js
│   └── templates/             # Jinja2 模板
```

## 常见问题

**"No module named 'uvicorn'"** → 运行 `dev_setup.bat` 重建虚拟环境。

**端口 8080 被占用** → 编辑 `run.py`，将 `port=8080` 改为其他端口。

## 数据管理

**数据库位置：**
- **打包模式（exe/安装包）：** `%APPDATA%\停车费管理系统\parking.db`
- **开发模式：** `./data/parking.db`

数据目录在卸载时**不会被删除**，因此重新安装应用会保留所有数据。

**自定义数据库路径：**
1. 以 `super_admin` 身份登录
2. 进入 ⚙️ 系统设置 → 数据库管理
3. 输入 SQLite 数据库文件的自定义路径
4. 保存并重启应用

**环境变量覆盖：**
```cmd
set PARKING_DB_URL=sqlite:///D:\data\my_parking.db
python run.py
```

**Schema 升级：** 应用在启动时自动应用 schema 迁移，升级应用版本无需手动干预即可保留现有数据。
