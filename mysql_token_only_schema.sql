-- Token 购买 + 大纲生成（无会员体系）MySQL 表结构
-- 适用：MySQL 8.0 / InnoDB / utf8mb4

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

CREATE TABLE IF NOT EXISTS users (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '用户ID',
  username VARCHAR(150) NOT NULL COMMENT '用户名（唯一）',
  email VARCHAR(191) NULL COMMENT '邮箱（可选，唯一）',
  phone VARCHAR(32) NULL COMMENT '手机号（可选，唯一）',
  password_hash VARCHAR(255) NOT NULL COMMENT '密码哈希',
  status TINYINT NOT NULL DEFAULT 1 COMMENT '状态：1正常，0禁用',
  token_balance BIGINT NOT NULL DEFAULT 0 COMMENT 'Token余额快照（真正一致性以账本流水为准）',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  last_login_at DATETIME NULL COMMENT '最后登录时间',
  UNIQUE KEY uk_users_username (username),
  UNIQUE KEY uk_users_email (email),
  UNIQUE KEY uk_users_phone (phone),
  KEY idx_users_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表';

CREATE TABLE IF NOT EXISTS token_products (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '商品ID',
  product_code VARCHAR(64) NOT NULL COMMENT '商品编码（唯一，如 token_10k）',
  name VARCHAR(64) NOT NULL COMMENT '商品名称',
  tokens BIGINT NOT NULL COMMENT '购买后增加的Token数量',
  price_cents INT NOT NULL COMMENT '价格（分）',
  status TINYINT NOT NULL DEFAULT 1 COMMENT '状态：1上架，0下架',
  UNIQUE KEY uk_token_products_code (product_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Token商品表';

CREATE TABLE IF NOT EXISTS payment_orders (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '订单ID',
  out_trade_no VARCHAR(64) NOT NULL COMMENT '商户订单号（唯一）',
  user_id BIGINT NOT NULL COMMENT '用户ID',
  channel VARCHAR(16) NOT NULL COMMENT '支付渠道：wechat/alipay',
  product_id BIGINT NOT NULL COMMENT 'Token商品ID（token_products.id）',
  amount_cents INT NOT NULL COMMENT '订单金额（分）',
  currency CHAR(3) NOT NULL DEFAULT 'CNY' COMMENT '币种（默认CNY）',
  status VARCHAR(16) NOT NULL COMMENT '订单状态：created/paying/paid/closed/refunded',
  provider_trade_no VARCHAR(128) NULL COMMENT '第三方交易号（微信/支付宝）',
  paid_at DATETIME NULL COMMENT '支付完成时间',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  UNIQUE KEY uk_orders_out_trade_no (out_trade_no),
  KEY idx_orders_user (user_id, created_at),
  KEY idx_orders_status (status, created_at),
  CONSTRAINT fk_orders_user FOREIGN KEY (user_id) REFERENCES users(id),
  CONSTRAINT fk_orders_product FOREIGN KEY (product_id) REFERENCES token_products(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='支付订单表';

CREATE TABLE IF NOT EXISTS payment_notifications (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '回调记录ID',
  order_id BIGINT NOT NULL COMMENT '关联订单ID（payment_orders.id）',
  channel VARCHAR(16) NOT NULL COMMENT '支付渠道：wechat/alipay',
  verify_ok TINYINT NOT NULL DEFAULT 0 COMMENT '验签是否通过：1通过，0失败',
  raw_headers TEXT NULL COMMENT '回调HTTP头原文（用于排查）',
  raw_body MEDIUMTEXT NULL COMMENT '回调Body原文（用于排查）',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  KEY idx_pay_notify_order (order_id, created_at),
  CONSTRAINT fk_pay_notify_order FOREIGN KEY (order_id) REFERENCES payment_orders(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='支付回调存证表';

CREATE TABLE IF NOT EXISTS token_ledger (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '账本流水ID',
  user_id BIGINT NOT NULL COMMENT '用户ID',
  delta BIGINT NOT NULL COMMENT 'Token变动：正数=入账，负数=扣费',
  balance_after BIGINT NOT NULL COMMENT '变动后的Token余额（快照）',
  biz_type VARCHAR(32) NOT NULL COMMENT '业务类型：recharge/consume/refund/manual',
  ref_type VARCHAR(32) NOT NULL COMMENT '关联类型：order/outline_job/...',
  ref_id VARCHAR(64) NOT NULL COMMENT '关联ID：商户订单号(out_trade_no)或任务ID等',
  meta JSON NULL COMMENT '附加信息（JSON，如模型/字数/渠道）',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  UNIQUE KEY uk_ledger_idem (biz_type, ref_type, ref_id),
  KEY idx_ledger_user (user_id, created_at),
  CONSTRAINT fk_ledger_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Token账本流水表（幂等发货与审计依据）';

CREATE TABLE IF NOT EXISTS outline_jobs (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '大纲生成任务ID',
  user_id BIGINT NOT NULL COMMENT '用户ID',
  status VARCHAR(16) NOT NULL COMMENT '任务状态：queued/running/succeeded/failed/canceled',
  provider VARCHAR(16) NOT NULL COMMENT '模型服务商：Gemini',
  model VARCHAR(64) NOT NULL COMMENT '模型名称/标识',
  request_json JSON NOT NULL COMMENT '生成请求参数（JSON，如类型/主题/章节数/扩写等）',
  result_text MEDIUMTEXT NULL COMMENT '生成结果：大纲全文',
  token_reserved BIGINT NOT NULL DEFAULT 0 COMMENT '预扣Token（可选）',
  token_cost BIGINT NOT NULL DEFAULT 0 COMMENT '最终消耗Token',
  error_message TEXT NULL COMMENT '失败原因（如有）',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  started_at DATETIME NULL COMMENT '开始时间',
  finished_at DATETIME NULL COMMENT '结束时间',
  KEY idx_jobs_user (user_id, created_at),
  KEY idx_jobs_status (status, created_at),
  CONSTRAINT fk_jobs_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='大纲生成任务表';

SET FOREIGN_KEY_CHECKS = 1;
