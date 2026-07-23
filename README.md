# YGOBanlist

YGOBanlist 是一个使用 Flask 开发的游戏王禁限卡表查询和维护工具。项目支持按地区与生效日期查看禁限卡表、查看卡片状态变化、在线编辑卡表，以及通过 CSV 文件导入卡片数据。

## 功能

- 按年份、生效日期和地区查询禁限卡表
- 查看完整卡表或仅查看状态变化
- 通过密码进入在线编辑页面
- 新建、修改和删除禁限卡表
- 新增、修改和删除卡片记录
- 从 CSV 文件导入卡片状态
- 默认使用 SQLite，也可以连接 MySQL

地区编号如下：

- 0 表示 OCG
- 1 表示 TCG
- 2 表示简体中文
- 3 表示大师决斗

卡片状态编号如下：

- 0 表示禁止
- 1 表示限制
- 2 表示准限制
- 3 表示无限制

## 环境要求

- Python 3.11 或更高版本
- 推荐使用 Python 3.12
- pip
- 可访问网络，以便从 ygocdb.com 获取卡片名称和类型

本项目已经在 Python 3.12 环境下完成运行验证。

## 安装

在项目根目录执行以下命令。

macOS 或 Linux：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Windows PowerShell：

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

如果本机没有名为 `python3.12` 的命令，可以将其替换为指向 Python 3.11 或更高版本的命令。

## 配置

项目提供了 `.env.example` 作为配置参考。复制该文件后，至少应修改 `SECRET_KEY` 和 `EDIT_PASSWORD`。

macOS 或 Linux：

```bash
cp .env.example .env
set -a
source .env
set +a
```

Windows PowerShell 可以直接设置环境变量：

```powershell
$env:SECRET_KEY = "replace-with-a-random-secret"
$env:EDIT_PASSWORD = "replace-with-an-edit-password"
$env:APP_PORT = "8888"
```

可用环境变量如下：

- `SECRET_KEY`：Flask 会话签名密钥。默认值仅适合本地开发
- `EDIT_PASSWORD`：进入在线编辑功能的密码。默认值为 `123456`
- `SQLALCHEMY_DATABASE_URI`：数据库连接地址。默认值为 `sqlite:///data.db`
- `SESSION_COOKIE_PATH`：部署在子路径时使用的会话 Cookie 路径。默认留空
- `APP_HOST`：监听地址。默认值为 `0.0.0.0`
- `APP_PORT`：监听端口。默认值为 `8888`
- `APP_DEBUG`：是否启用 Flask 调试模式。可使用 `true` 或 `false`

生产环境必须设置随机且不可预测的 `SECRET_KEY`，并修改默认编辑密码。

## 运行

激活虚拟环境并加载环境变量后执行：

```bash
python run.py
```

默认访问地址：

```text
http://127.0.0.1:8888
```

在线编辑页面不会显示在主界面导航中，可以直接访问：

```text
http://127.0.0.1:8888/manage
```

原有的 `/edit` 路径仍然保留兼容。

如果 8888 端口已被占用，可以修改端口后启动：

macOS 或 Linux：

```bash
APP_PORT=5055 python run.py
```

Windows PowerShell：

```powershell
$env:APP_PORT = "5055"
python run.py
```

## 数据库

默认使用 SQLite。首次启动时，Flask-SQLAlchemy 会自动创建数据表和索引，数据库文件位于：

```text
instance/data.db
```

如果需要使用 MySQL，请先创建数据库，然后设置连接地址：

```bash
export SQLALCHEMY_DATABASE_URI="mysql+pymysql://user:password@127.0.0.1:3306/ygobanlist?charset=utf8mb4"
```

项目中的 `seed.py` 可以写入少量示例数据：

```bash
python seed.py
```

脚本可以重复运行。已经存在的卡表和卡片会被复用或更新。

## CSV 导入格式

CSV 文件不需要表头，每行包含三列：

```text
卡片 CID,过去状态,当前状态
```

示例：

```csv
69272449,1,0
32061192,3,2
```

导入时，状态值必须为 0、1、2 或 3。CSV 中存在无效数字、卡片 CID 或状态时，本次导入会被拒绝，不会提交部分数据。

## 架构说明

项目使用分层结构组织代码：

- `routes` 只处理 HTTP 请求、响应和页面跳转
- `web` 负责参数解析、认证状态和导航
- `services` 负责业务规则、数据库事务和页面数据组装
- `models` 负责数据库模型与关系
- `extensions` 负责 Flask 扩展实例
- `database` 负责表和索引初始化
- `templates/editor` 存放编辑页的独立界面组件
- `static/css` 按基础布局、通用组件和编辑页面组织样式

公开查询与后台编辑使用两个独立 Blueprint。编辑操作统一调用服务层，因此页面路由不再直接编写数据库查询和事务逻辑。

前端样式入口为 `app/static/style.css`。该文件只加载基础样式和通用组件样式，编辑页通过模板按需加载 `editor.css`，避免公开页面加载不需要的后台样式。

## 项目结构

```text
YGOBanlist
app
app/static
app/static/css
app/templates
app/templates/editor
app/routes
app/services
app/web
app/app.py
app/card_info.py
app/card_list_parser.py
app/database.py
app/extensions.py
app/models.py
tests
requirements.txt
run.py
seed.py
```

主要文件说明：

- `run.py`：本地启动入口
- `app/app.py`：Flask 应用工厂
- `app/routes/public.py`：公开查询页面路由
- `app/routes/editor.py`：编辑页面和操作路由
- `app/services/banlists.py`：卡表和卡片业务操作
- `app/services/presentation.py`：页面展示数据组装
- `app/web/params.py`：请求参数解析和校验
- `app/templates/editor`：编辑页模板组件
- `app/static/css/base.css`：页面布局和侧边栏样式
- `app/static/css/components.css`：表格、表单和状态组件样式
- `app/static/css/editor.css`：编辑页面专用样式
- `app/models.py`：数据库模型
- `app/card_info.py`：远程卡片信息查询
- `app/card_list_parser.py`：CSV 文件解析
- `seed.py`：示例数据脚本

## 测试

运行全部回归测试：

```bash
python -m unittest discover -v
```

测试使用内存 SQLite 数据库，不会修改 `instance/data.db`。测试中的卡片信息查询使用本地模拟数据，不依赖外部网络。

## 常见问题

页面显示未知卡片：

项目会访问 ygocdb.com 查询卡片数据。如果网络不可用、请求超时或卡片 CID 不存在，页面会显示未知卡片，但本地禁限卡表数据仍可正常使用。

编辑密码无效：

确认运行应用的终端已经设置 `EDIT_PASSWORD`。修改环境变量后需要重新启动应用。

数据库连接失败：

确认 `SQLALCHEMY_DATABASE_URI` 格式正确。使用 MySQL 时，还需要确认数据库已经创建、账号具有访问权限，并且 MySQL 服务正在运行。
