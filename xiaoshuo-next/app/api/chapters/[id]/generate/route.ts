import { NextRequest } from 'next/server'
import { requireAuth } from '@/lib/auth-utils'
import { prisma } from '@/lib/db'
import { getAIService } from '@/lib/ai-service'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const chapterId = parseInt(params.id)

  try {
    const user = await requireAuth()
    const body = await request.json()
    const { novelType, novelTheme, novelOutline, prevContent } = body

    // 获取章节信息
    const chapter = await prisma.chapter.findUnique({
      where: { id: chapterId },
      include: {
        novel: true,
      },
    })

    if (!chapter || chapter.novel.userId !== user.id) {
      return new Response(JSON.stringify({ error: '章节不存在' }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' },
      })
    }

    if (chapter.status === 'completed') {
      return new Response(JSON.stringify({ error: '章节已生成' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      })
    }

    // 检查余额
    const COST = 1000
    if (user.tokenBalance < COST) {
      return new Response(JSON.stringify({ error: '余额不足' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      })
    }

    // 扣除余额
    await prisma.user.update({
      where: { id: user.id },
      data: {
        tokenBalance: {
          decrement: COST,
        },
      },
    })

    // 更新章节状态
    await prisma.chapter.update({
      where: { id: chapterId },
      data: {
        status: 'generating',
        cost: COST,
      },
    })

    // 创建流式响应
    const encoder = new TextEncoder()
    const stream = new ReadableStream({
      async start(controller) {
        try {
          const aiService = getAIService('gemini')

          let accumulatedContent = ''

          // 使用流式生成
          for await (const chunk of aiService.generateChapterStream(
            novelType,
            novelTheme,
            novelOutline,
            chapter.chapterNum,
            chapter.title || '',
            chapter.summary || '',
            prevContent
          )) {
            accumulatedContent += chunk
            controller.enqueue(encoder.encode(chunk))
          }

          // 生成完成，更新数据库
          const wordCount = accumulatedContent.length
          await prisma.chapter.update({
            where: { id: chapterId },
            data: {
              content: accumulatedContent,
              wordCount,
              status: 'completed',
            },
          })

          controller.close()
        } catch (error: any) {
          console.error('Generation error:', error)

          // 失败退款
          await prisma.user.update({
            where: { id: user.id },
            data: {
              tokenBalance: {
                increment: COST,
              },
            },
          })

          await prisma.chapter.update({
            where: { id: chapterId },
            data: {
              status: 'pending',
              cost: 0,
            },
          })

          controller.error(error)
        }
      },
    })

    return new Response(stream, {
      headers: {
        'Content-Type': 'text/plain; charset=utf-8',
        'Transfer-Encoding': 'chunked',
      },
    })
  } catch (error: any) {
    console.error('API error:', error)
    return new Response(JSON.stringify({ error: error.message || '生成失败' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    })
  }
}
