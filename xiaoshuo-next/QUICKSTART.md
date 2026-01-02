# 快速启动指南

## 5分钟快速上手

### 1. 安装依赖（2分钟）

```bash
cd xiaoshuo-next
npm install
```

### 2. 配置环境变量（1分钟）

创建 `.env` 文件：

```bash
cp .env.example .env
```

**最小配置（SQLite开发环境）：**

```env
# 使用SQLite（无需安装MySQL）
DATABASE_URL="file:./dev.db"

# NextAuth配置
NEXTAUTH_URL="http://localhost:3000"
NEXTAUTH_SECRET="dev-secret-change-in-production"

# AI配置（必需）
GEMINI_API_KEY="your-gemini-api-key"
```

> 📌 **获取Gemini API Key**:
> 1. 访问 https://makersuite.google.com/app/apikey
> 2. 登录Google账号
> 3. 创建API Key并复制

### 3. 初始化数据库（1分钟）

**使用SQLite（推荐开发）：**

1. 修改 `prisma/schema.prisma`：
```prisma
datasource db {
  provider = "sqlite"  // 改为sqlite
  url      = env("DATABASE_URL")
}
```

2. 运行初始化：
```bash
npm run db:generate
npm run db:push
```

### 4. 启动开发服务器（1分钟）

```bash
npm run dev
```

访问: http://localhost:3000

### 5. 开始使用

1. **注册账号**: 访问注册页面创建账号
2. **生成大纲**: 点击"AI生成大纲"，选择类型和主题
3. **生成章节**: 在小说详情页点击"生成正文"

---

## 生产环境部署（MySQL）

### 1. 准备MySQL数据库

```sql
CREATE DATABASE xiaoshuo CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'xiaoshuo_user'@'localhost' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON xiaoshuo.* TO 'xiaoshuo_user'@'localhost';
FLUSH PRIVILEGES;
```

### 2. 配置环境变量

```env
DATABASE_URL="mysql://xiaoshuo_user:your_password@localhost:3306/xiaoshuo"
NEXTAUTH_URL="https://your-domain.com"
NEXTAUTH_SECRET="$(openssl rand -base64 32)"
GEMINI_API_KEY="your-gemini-api-key"
```

### 3. 修改Schema并部署

```bash
# 1. 修改 prisma/schema.prisma
datasource db {
  provider = "mysql"
  url      = env("DATABASE_URL")
}

# 2. 生成迁移
npx prisma migrate deploy

# 3. 构建项目
npm run build

# 4. 启动生产服务器
npm start
```

---

## Vercel一键部署

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new)

### 部署步骤：

1. **Fork仓库**到你的GitHub账号

2. **导入到Vercel**:
   - 访问 https://vercel.com/new
   - 选择你的仓库
   - 点击Import

3. **配置环境变量**:
   ```
   DATABASE_URL=mysql://user:pass@host:3306/db
   NEXTAUTH_URL=https://your-app.vercel.app
   NEXTAUTH_SECRET=random-secret-key
   GEMINI_API_KEY=your-api-key
   ```

4. **部署数据库**（推荐PlanetScale）:
   - 访问 https://planetscale.com
   - 创建免费数据库
   - 复制连接字符串到 `DATABASE_URL`

5. **点击Deploy**

6. **初始化数据库**:
   ```bash
   # 本地运行
   npx prisma migrate deploy
   ```

---

## Docker部署

### 使用Docker Compose

```bash
# 1. 创建 docker-compose.yml（已包含在项目中）

# 2. 启动服务
docker-compose up -d

# 3. 访问
http://localhost:3000
```

---

## 故障排查

### 问题1: `npm install` 失败
```bash
# 清除缓存重试
rm -rf node_modules package-lock.json
npm install
```

### 问题2: Prisma Client未生成
```bash
npx prisma generate
```

### 问题3: 数据库连接失败
```bash
# 检查MySQL是否运行
mysql -u root -p

# 测试连接
npx prisma db push
```

### 问题4: API Key无效
- 检查 `.env` 文件中的 `GEMINI_API_KEY`
- 确保API Key有效且未过期
- 检查API配额

---

## 常用命令

```bash
# 开发
npm run dev          # 启动开发服务器
npm run build        # 构建生产版本
npm start            # 启动生产服务器

# 数据库
npm run db:generate  # 生成Prisma Client
npm run db:push      # 推送Schema到数据库
npm run db:studio    # 打开数据库管理界面

# 代码质量
npm run lint         # 运行ESLint检查
```

---

## 下一步

- 📖 阅读完整 [README.md](./README.md)
- 🔧 查看 [CLAUDE.md](../CLAUDE.md) 了解项目架构
- 🎨 自定义UI主题和样式
- 🚀 部署到生产环境

---

需要帮助？查看项目文档或提交Issue。
