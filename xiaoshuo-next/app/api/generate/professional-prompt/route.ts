import { NextRequest } from 'next/server'
import { requireAuth } from '@/lib/auth-utils'
import { getAIService } from '@/lib/ai-service'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function POST(request: NextRequest) {
  try {
    const user = await requireAuth()
    const body = await request.json()
    const { type, theme, writingIdea } = body

    if (!type || !theme) {
      return new Response(JSON.stringify({ error: '请填写类型和主题' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      })
    }

    const aiService = getAIService('gemini')

    // 生成专业提示词
    const prompt = await aiService.generateProfessionalPrompt(
      type,
      theme,
      writingIdea || ''
    )

    return new Response(JSON.stringify({ prompt }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  } catch (error: any) {
    console.error('Professional prompt generation error:', error)
    return new Response(
      JSON.stringify({ error: error.message || '生成失败' }),
      {
        status: 500,
        headers: { 'Content-Type': 'application/json' },
      }
    )
  }
}
