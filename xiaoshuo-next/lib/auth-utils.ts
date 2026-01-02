/**
 * 认证工具函数
 */

import { getServerSession } from 'next-auth'
import { authOptions } from './auth'
import { prisma } from './db'

/**
 * 获取当前登录用户
 */
export async function getCurrentUser() {
  const session = await getServerSession(authOptions)

  if (!session?.user?.id) {
    return null
  }

  const user = await prisma.user.findUnique({
    where: { id: parseInt(session.user.id) },
    select: {
      id: true,
      username: true,
      email: true,
      phone: true,
      tokenBalance: true,
      status: true,
      createdAt: true,
      lastLoginAt: true,
    },
  })

  return user
}

/**
 * 要求用户已登录，否则抛出错误
 */
export async function requireAuth() {
  const user = await getCurrentUser()

  if (!user) {
    throw new Error('未登录')
  }

  return user
}
