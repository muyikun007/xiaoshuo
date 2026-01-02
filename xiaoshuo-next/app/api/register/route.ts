import { NextRequest, NextResponse } from 'next/server'
import { hash } from 'bcryptjs'
import { prisma } from '@/lib/db'

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const { username, password, email } = body

    if (!username || !password) {
      return NextResponse.json(
        { error: '请输入用户名和密码' },
        { status: 400 }
      )
    }

    // 检查用户名是否已存在
    const existingUser = await prisma.user.findUnique({
      where: { username },
    })

    if (existingUser) {
      return NextResponse.json(
        { error: '用户名已存在' },
        { status: 400 }
      )
    }

    // 哈希密码
    const passwordHash = await hash(password, 12)

    // 创建用户
    const user = await prisma.user.create({
      data: {
        username,
        passwordHash,
        email: email || null,
        tokenBalance: 10000, // 初始赠送10000积分
        status: 1,
      },
    })

    return NextResponse.json({
      success: true,
      user: {
        id: user.id,
        username: user.username,
        tokenBalance: user.tokenBalance,
      },
    })
  } catch (error) {
    console.error('Registration error:', error)
    return NextResponse.json(
      { error: '注册失败，请重试' },
      { status: 500 }
    )
  }
}
