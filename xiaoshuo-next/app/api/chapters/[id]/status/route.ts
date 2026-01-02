import { NextRequest, NextResponse } from 'next/server'
import { requireAuth } from '@/lib/auth-utils'
import { prisma } from '@/lib/db'

export async function GET(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  try {
    const user = await requireAuth()
    const chapterId = parseInt(params.id)

    const chapter = await prisma.chapter.findUnique({
      where: { id: chapterId },
      include: {
        novel: {
          select: {
            userId: true,
          },
        },
      },
    })

    if (!chapter || chapter.novel.userId !== user.id) {
      return NextResponse.json({ error: '章节不存在' }, { status: 404 })
    }

    return NextResponse.json({
      status: chapter.status,
      content: chapter.content || '',
      wordCount: chapter.wordCount,
      cost: chapter.cost,
    })
  } catch (error: any) {
    return NextResponse.json(
      { error: error.message || '获取失败' },
      { status: 500 }
    )
  }
}
