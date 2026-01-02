/**
 * AI服务集成模块
 * 支持Google Gemini API进行大纲和章节生成
 */

import { GoogleGenerativeAI, GenerativeModel } from '@google/generative-ai'

// 默认模型配置
const DEFAULT_GEMINI_MODEL = 'gemini-2.0-flash-exp'

// AI提供商类型
export type AIProvider = 'gemini' | 'doubao' | 'claude'

// 生成配置
export interface GenerationConfig {
  temperature?: number
  maxOutputTokens?: number
  topP?: number
}

/**
 * 构建大纲生成的系统指令
 */
function buildSystemInstruction(): string {
  return `你是资深网络小说策划编辑，擅长打造强爽点节奏的长篇网文。
你的任务是按要求输出完整的中文小说大纲，语言简洁有力。
输出要求：
1) 作品名
2) 类型
3) 核心人设（主角、对手、导师、盟友）
4) 世界观与设定（时代、地域、权力结构、资源）
5) 爽点清单（10条以上，明确冲突与反转）
6) 三幕结构梗概（每幕5-8个关键节点）
7) 章节大纲（至少24章，每章包含标题与1-2句梗概，推进冲突与爽点）
8) 可扩展支线与后续走向
风格：节奏快、冲突密集、反转频繁、爽点直给。
重要提示：章节标题中请勿包含"第X章"前缀，仅输出纯标题，例如"风起云涌"而不是"第1章 风起云涌"。`
}

/**
 * 构建约束条件
 */
function buildConstraints(novelType: string, theme: string): string {
  return `类型：${novelType}
主题/设定：${theme}
必须严格对齐类型与主题，使用中文，本土现实语境。
不得引入仙侠、修真、灵气、法术、赛博、星际、外星、末日等元素。
世界观与角色设定需贴近现实逻辑，避免科幻或玄幻成分。`
}

/**
 * AI服务类
 */
export class AIService {
  private apiKey: string
  private provider: AIProvider
  private modelName: string
  private genAI: GoogleGenerativeAI | null = null

  constructor(
    apiKey: string,
    provider: AIProvider = 'gemini',
    modelName?: string
  ) {
    this.apiKey = apiKey
    this.provider = provider
    this.modelName = modelName || DEFAULT_GEMINI_MODEL

    if (provider === 'gemini') {
      this.genAI = new GoogleGenerativeAI(apiKey)
    }
  }

  /**
   * 清理生成的文本，移除无关内容
   */
  private sanitizeText(text: string): string {
    if (!text) return ''

    const lines: string[] = []
    const badPrefixes = [
      '收到',
      '感谢',
      '作为资深',
      '我将',
      '我会',
      '策划案',
      '以下是',
      '将为您',
      '为了确保',
      '基于您',
      '这里为您提供',
    ]

    for (const line of text.split('\n')) {
      const trimmed = line.trim()
      if (!trimmed) continue

      const hasBadPrefix = badPrefixes.some((prefix) =>
        trimmed.startsWith(prefix)
      )
      if (hasBadPrefix) continue

      lines.push(trimmed)
    }

    return lines.join('\n')
  }

  /**
   * 调用Gemini API
   */
  private async callGemini(
    prompt: string,
    systemInstruction?: string,
    config?: GenerationConfig
  ): Promise<string> {
    if (!this.genAI) {
      throw new Error('Gemini AI not initialized')
    }

    const model = this.genAI.getGenerativeModel({
      model: this.modelName,
      systemInstruction: systemInstruction,
    })

    const generationConfig = {
      temperature: config?.temperature ?? 0.7,
      maxOutputTokens: config?.maxOutputTokens ?? 8000,
      topP: config?.topP ?? 0.95,
    }

    try {
      const result = await model.generateContent({
        contents: [{ role: 'user', parts: [{ text: prompt }] }],
        generationConfig,
      })

      const response = result.response
      return response.text()
    } catch (error) {
      console.error('Gemini API Error:', error)
      throw error
    }
  }

  /**
   * 生成完整大纲
   */
  async generateOutline(novelType: string, theme: string): Promise<string> {
    const systemInstruction = buildSystemInstruction()
    const constraints = buildConstraints(novelType, theme)

    const prompt = `${constraints}\n\n请根据以上要求生成完整的小说大纲。`

    const result = await this.callGemini(prompt, systemInstruction, {
      temperature: 0.8,
      maxOutputTokens: 8000,
    })

    return this.sanitizeText(result)
  }

  /**
   * 生成单个章节内容
   */
  async generateChapter(
    novelType: string,
    theme: string,
    outline: string,
    chapterNum: number,
    chapterTitle: string,
    chapterSummary: string,
    prevContent?: string
  ): Promise<string> {
    const contextBase = `小说类型：${novelType}
主题：${theme}
完整大纲参考：
${outline}`

    let prevContextPrompt = ''
    if (prevContent) {
      const prevSegment = prevContent.slice(-2000)
      prevContextPrompt = `【上一章（第${chapterNum - 1}章）结尾内容回顾】
${prevSegment}
--------------------------------
指令：请务必紧接上一章的结尾剧情继续创作，保持场景、时间、人物状态的连贯性。

`
    }

    const prompt = `你是一位专业畅销小说作家。
任务：请根据提供的大纲和上下文，创作小说第${chapterNum}章的正文。
章节标题：${chapterTitle}
本章梗概：${chapterSummary}

${prevContextPrompt}【小说完整大纲与设定】
${contextBase}

要求：
1. 字数要求：2000字以上。
2. 剧情紧凑，场景描写生动，人物对话符合性格。
3. 严格贴合本章梗概，承接上文（如果有），铺垫下文。
4. 输出纯正文内容，不要包含"第X章"标题，直接开始正文描写。`

    const result = await this.callGemini(prompt, undefined, {
      temperature: 0.8,
      maxOutputTokens: 8000,
    })

    return this.sanitizeText(result)
  }

  /**
   * 流式生成章节内容
   * 返回一个可读流
   */
  async *generateChapterStream(
    novelType: string,
    theme: string,
    outline: string,
    chapterNum: number,
    chapterTitle: string,
    chapterSummary: string,
    prevContent?: string
  ): AsyncGenerator<string, void, unknown> {
    if (!this.genAI) {
      throw new Error('Gemini AI not initialized')
    }

    const contextBase = `小说类型：${novelType}
主题：${theme}
完整大纲参考：
${outline}`

    let prevContextPrompt = ''
    if (prevContent) {
      const prevSegment = prevContent.slice(-2000)
      prevContextPrompt = `【上一章（第${chapterNum - 1}章）结尾内容回顾】
${prevSegment}
--------------------------------
指令：请务必紧接上一章的结尾剧情继续创作，保持场景、时间、人物状态的连贯性。

`
    }

    const prompt = `你是一位专业畅销小说作家。
任务：请根据提供的大纲和上下文，创作小说第${chapterNum}章的正文。
章节标题：${chapterTitle}
本章梗概：${chapterSummary}

${prevContextPrompt}【小说完整大纲与设定】
${contextBase}

要求：
1. 字数要求：2000字以上。
2. 剧情紧凑，场景描写生动，人物对话符合性格。
3. 严格贴合本章梗概，承接上文（如果有），铺垫下文。
4. 输出纯正文内容，不要包含"第X章"标题，直接开始正文描写。`

    const model = this.genAI.getGenerativeModel({
      model: this.modelName,
    })

    const generationConfig = {
      temperature: 0.8,
      maxOutputTokens: 8000,
      topP: 0.95,
    }

    const result = await model.generateContentStream({
      contents: [{ role: 'user', parts: [{ text: prompt }] }],
      generationConfig,
    })

    for await (const chunk of result.stream) {
      const chunkText = chunk.text()
      if (chunkText) {
        yield chunkText
      }
    }
  }
}

/**
 * 获取AI服务实例
 */
export function getAIService(provider: AIProvider = 'gemini'): AIService {
  let apiKey: string | undefined

  switch (provider) {
    case 'gemini':
      apiKey = process.env.GEMINI_API_KEY
      break
    case 'doubao':
      apiKey = process.env.DOUBAO_API_KEY
      break
    case 'claude':
      apiKey = process.env.CLAUDE_API_KEY
      break
  }

  if (!apiKey) {
    throw new Error(`API key for provider ${provider} not found`)
  }

  return new AIService(apiKey, provider)
}
