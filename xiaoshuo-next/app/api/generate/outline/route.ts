import { NextRequest } from 'next/server'
import { requireAuth } from '@/lib/auth-utils'
import { getAIService } from '@/lib/ai-service'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function POST(request: NextRequest) {
  try {
    const user = await requireAuth()
    const body = await request.json()
    const { type, theme, writingIdea, professionalPrompt } = body

    if (!type || !theme) {
      return new Response(JSON.stringify({ error: '请填写类型和主题' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      })
    }

    // 创建流式响应
    const encoder = new TextEncoder()
    const stream = new ReadableStream({
      async start(controller) {
        try {
          const aiService = getAIService('gemini')

          // 生成大纲，传入写作思路和专业提示词
          const outline = await aiService.generateOutline(
            type,
            theme,
            writingIdea,
            professionalPrompt
          )

          // 模拟流式输出以提供更好的用户体验
          const chunks = outline.split('\n')
          for (const chunk of chunks) {
            controller.enqueue(encoder.encode(chunk + '\n'))
            // 小延迟以模拟流式效果
            await new Promise((resolve) => setTimeout(resolve, 50))
          }

          controller.close()
        } catch (error: any) {
          console.error('Outline generation error:', error)
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
