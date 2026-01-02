import { NextRequest, NextResponse } from 'next/server'
import { requireAuth } from '@/lib/auth-utils'
import { prisma } from '@/lib/db'
import { parseOutlineText } from '@/lib/outline-parser'

export async function GET() {
  try {
    const user = await requireAuth()

    const novels = await prisma.novel.findMany({
      where: { userId: user.id },
      orderBy: { createdAt: 'desc' },
      include: {
        chapters: {
          select: {
            id: true,
            chapterNum: true,
            title: true,
            status: true,
          },
        },
      },
    })

    return NextResponse.json({ novels })
  } catch (error: any) {
    return NextResponse.json(
      { error: error.message || '获取失败' },
      { status: 401 }
    )
  }
}

export async function POST(request: NextRequest) {
  try {
    const user = await requireAuth()
    const body = await request.json()
    const { title, type, theme, outline } = body

    if (!title || !type || !theme || !outline) {
      return NextResponse.json(
        { error: '请填写所有必填项' },
        { status: 400 }
      )
    }

    // 解析大纲提取章节
    const parsedChapters = parseOutlineText(outline)

    if (parsedChapters.length === 0) {
      return NextResponse.json(
        { error: '无法解析大纲，请确保包含"第X章"格式' },
        { status: 400 }
      )
    }

    // 创建小说记录
    const novel = await prisma.novel.create({
      data: {
        userId: user.id,
        title,
        type,
        theme,
        outline,
        chapters: {
          create: parsedChapters.map((pc) => ({
            chapterNum: pc.chapter,
            title: pc.title,
            summary: pc.summary,
            status: 'pending',
          })),
        },
      },
      include: {
        chapters: true,
      },
    })

    return NextResponse.json(novel)
  } catch (error: any) {
    console.error('Create novel error:', error)
    return NextResponse.json(
      { error: error.message || '创建失败' },
      { status: 500 }
    )
  }
}
