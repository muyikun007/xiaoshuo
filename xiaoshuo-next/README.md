# 小说大纲生成器 - Next.js版本

基于Next.js 14、TypeScript、Prisma ORM重构的AI驱动中文网络小说大纲和内容生成工具。

## ✨ 功能特性

- 🎯 **AI智能大纲生成**: 基于Google Gemini API，支持40+小说类型，3-5分钟生成完整大纲
- ✍️ **章节内容生成**: 智能生成2000字以上章节正文，剧情连贯，人物鲜活
- 📝 **流式输出**: 实时预览生成内容，提升用户体验
- 🔐 **用户认证系统**: 基于NextAuth.js的完整用户注册/登录系统
- 💰 **积分系统**: Token余额管理，按字数计费
- 📚 **小说项目管理**: 创建、查看、导出小说作品
- 🎨 **现代化UI**: 基于TailwindCSS + shadcn/ui的精美界面

## 🛠️ 技术栈

### 核心框架
- **Next.js 14** - React服务端渲染框架（App Router）
- **TypeScript** - 类型安全的JavaScript超集
- **React 18** - UI构建库

### 数据库 & ORM
- **Prisma** - 下一代ORM工具
- **MySQL** - 生产环境数据库
- **SQLite** - 开发环境数据库（可选）

### 身份验证
- **NextAuth.js** - Next.js官方认证解决方案
- **bcryptjs** - 密码加密

### AI集成
- **Google Generative AI SDK** - Gemini API客户端
- 支持流式响应和异步生成

### UI框架
- **TailwindCSS** - 实用优先的CSS框架
- **shadcn/ui** - 高质量React组件库
- **Lucide React** - 精美图标库
- **React Hot Toast** - 通知提示组件

### 数据获取
- **TanStack Query (React Query)** - 强大的异步状态管理

## 📦 安装部署

### 前置要求

- Node.js 18+
- MySQL 5.7+ 或 MariaDB 10.3+
- Google Gemini API Key

### 1. 克隆项目

```bash
cd xiaoshuo-next
```

### 2. 安装依赖

```bash
npm install
```

### 3. 配置环境变量

复制 `.env.example` 为 `.env`：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
# 数据库连接
DATABASE_URL="mysql://user:password@localhost:3306/xiaoshuo?schema=public"

# NextAuth配置
NEXTAUTH_URL="http://localhost:3000"
NEXTAUTH_SECRET="your-secret-key-change-this"

# AI服务配置
GEMINI_API_KEY="your-gemini-api-key"
```

### 4. 初始化数据库

```bash
# 生成Prisma Client
npm run db:generate

# 推送数据库Schema
npm run db:push

# 或者使用Prisma Migrate
npx prisma migrate dev --name init
```

### 5. 启动开发服务器

```bash
npm run dev
```

访问 http://localhost:3000

### 6. 生产环境构建

```bash
npm run build
npm start
```

## 📁 项目结构

```
xiaoshuo-next/
├── app/                          # Next.js App Router
│   ├── (auth)/                   # 认证路由组
│   │   ├── login/               # 登录页面
│   │   └── register/            # 注册页面
│   ├── dashboard/               # 仪表盘
│   │   ├── create-novel/       # 手动创建小说
│   │   └── generate-outline/   # AI生成大纲
│   ├── novel/[id]/             # 小说详情页
│   ├── api/                     # API路由
│   │   ├── auth/               # NextAuth API
│   │   ├── register/           # 注册接口
│   │   ├── novels/             # 小说CRUD
│   │   ├── chapters/           # 章节管理
│   │   └── generate/           # AI生成接口
│   ├── layout.tsx              # 根布局
│   ├── page.tsx                # 首页
│   ├── providers.tsx           # 全局Provider
│   └── globals.css             # 全局样式
├── components/                  # React组件
│   ├── ui/                     # UI基础组件
│   │   ├── button.tsx
│   │   ├── input.tsx
│   │   ├── card.tsx
│   │   └── nav.tsx
│   ├── novel/                  # 小说相关组件
│   │   ├── chapter-list.tsx
│   │   └── chapter-item.tsx
│   └── auth/                   # 认证组件
├── lib/                         # 工具库
│   ├── db.ts                   # Prisma Client
│   ├── auth.ts                 # NextAuth配置
│   ├── auth-utils.ts           # 认证工具函数
│   ├── ai-service.ts           # AI服务封装
│   ├── outline-parser.ts       # 大纲解析器
│   └── utils.ts                # 通用工具函数
├── prisma/                      # Prisma配置
│   └── schema.prisma           # 数据库Schema
├── types/                       # TypeScript类型定义
│   └── next-auth.d.ts
├── public/                      # 静态资源
├── .env.example                 # 环境变量模板
├── .gitignore
├── next.config.js              # Next.js配置
├── tailwind.config.ts          # TailwindCSS配置
├── tsconfig.json               # TypeScript配置
├── package.json
└── README.md
```

## 🔑 核心功能说明

### 1. 用户认证

基于NextAuth.js的Credentials Provider实现：
- 用户注册（自动赠送10000积分）
- 密码加密存储（bcrypt）
- 基于JWT的会话管理
- 服务端和客户端认证状态管理

### 2. AI大纲生成

**流程：**
1. 用户选择小说类型（都市、官场、商战等）
2. 输入主题和设定描述
3. 调用Google Gemini API生成完整大纲
4. 流式输出，实时显示生成进度
5. 自动解析章节信息存入数据库

**大纲格式：**
- 作品名、类型、人设
- 世界观与设定
- 爽点清单
- 三幕结构梗概
- 章节大纲（第X章 标题：梗概）

### 3. 章节内容生成

**流程：**
1. 点击章节"生成正文"按钮
2. 系统检查用户余额（预计消耗1000积分）
3. 扣除积分并标记章节为"生成中"
4. 调用AI服务流式生成章节内容
5. 实时显示生成内容
6. 完成后更新字数和实际消耗

**特性：**
- 支持流式输出（ReadableStream）
- 自动承接上一章内容
- 生成失败自动退款
- 2000字以上正文

### 4. 大纲解析

支持从大纲文本中自动提取章节：
- 中文格式：`第X章 标题：内容`
- 英文格式：`Chapter X 标题：内容`
- 自动排序和去重

## 🔧 配置说明

### 数据库配置

**MySQL（推荐生产环境）：**
```env
DATABASE_URL="mysql://user:password@localhost:3306/xiaoshuo"
```

**SQLite（开发环境）：**
```env
DATABASE_URL="file:./dev.db"
```

修改 `prisma/schema.prisma` 中的 provider：
```prisma
datasource db {
  provider = "sqlite"  // 或 "mysql"
  url      = env("DATABASE_URL")
}
```

### AI服务配置

目前支持Google Gemini API：

1. 获取API Key: https://makersuite.google.com/app/apikey
2. 配置环境变量:
```env
GEMINI_API_KEY="your-api-key-here"
```

3. 修改模型（可选）:
```typescript
// lib/ai-service.ts
const DEFAULT_GEMINI_MODEL = 'gemini-2.0-flash-exp'
```

## 📊 数据库Schema

### User (用户表)
- id: 用户ID
- username: 用户名（唯一）
- passwordHash: 密码哈希
- tokenBalance: Token余额
- status: 账户状态

### Novel (小说表)
- id: 小说ID
- userId: 所属用户
- title: 作品名
- type: 类型
- theme: 主题
- outline: 完整大纲

### Chapter (章节表)
- id: 章节ID
- novelId: 所属小说
- chapterNum: 章节号
- title: 章节标题
- summary: 梗概
- content: 正文内容
- status: 状态（pending/generating/completed）
- wordCount: 字数
- cost: 消耗积分

## 🚀 部署建议

### Vercel部署

1. 推送代码到GitHub
2. 在Vercel导入项目
3. 配置环境变量
4. 配置外部MySQL数据库（如PlanetScale、Railway）
5. 部署

### Docker部署

创建 `docker-compose.yml`:

```yaml
version: '3.8'
services:
  app:
    build: .
    ports:
      - "3000:3000"
    environment:
      - DATABASE_URL=mysql://user:pass@db:3306/xiaoshuo
      - NEXTAUTH_SECRET=your-secret
      - GEMINI_API_KEY=your-key
    depends_on:
      - db

  db:
    image: mysql:8
    environment:
      MYSQL_ROOT_PASSWORD: rootpass
      MYSQL_DATABASE: xiaoshuo
      MYSQL_USER: user
      MYSQL_PASSWORD: pass
    volumes:
      - mysql-data:/var/lib/mysql

volumes:
  mysql-data:
```

## 🤝 与原项目对比

| 功能 | Flask/FastAPI版本 | Next.js版本 |
|-----|------------------|------------|
| 框架 | Flask + FastAPI | Next.js 14 |
| 语言 | Python | TypeScript |
| ORM | SQLAlchemy | Prisma |
| 认证 | Flask-Login | NextAuth.js |
| UI | Jinja2模板 | React + TailwindCSS |
| 状态管理 | jQuery | React Query |
| 部署 | Gunicorn/Uvicorn | Vercel/Node.js |

**优势：**
- ✅ 更好的类型安全（TypeScript）
- ✅ 更现代的UI体验（React）
- ✅ 更好的SEO（SSR）
- ✅ 更简单的部署（Vercel）
- ✅ 更好的开发体验（HMR）

## 📝 开发指南

### 添加新的AI Provider

1. 在 `lib/ai-service.ts` 中添加新的provider类型
2. 实现对应的API调用逻辑
3. 更新环境变量配置

### 自定义UI主题

修改 `tailwind.config.ts` 中的颜色变量。

### 数据库迁移

```bash
# 创建迁移
npx prisma migrate dev --name your_migration_name

# 应用迁移
npx prisma migrate deploy

# 查看数据库
npx prisma studio
```

## 🐛 常见问题

**Q: Prisma Client生成失败？**
A: 运行 `npm run db:generate` 重新生成。

**Q: 数据库连接失败？**
A: 检查 `DATABASE_URL` 格式和数据库服务状态。

**Q: AI生成失败？**
A: 检查 `GEMINI_API_KEY` 是否正确，以及API额度。

**Q: 流式输出不工作？**
A: 确保使用Node.js运行时，不要使用Edge Runtime。

## 📄 License

本项目继承原项目的开源协议。

## 🙏 致谢

- 原Flask/FastAPI版本作者
- Google Gemini Team
- Next.js Team
- Prisma Team
- shadcn/ui

---

**作者**: Claude AI Assistant
**创建时间**: 2026-01-02
**版本**: 1.0.0
