/**
 * 大纲解析工具
 * 从大纲文本中提取章节信息
 */

export interface ParsedChapter {
  chapter: number
  title: string
  summary: string
}

/**
 * 解析大纲文本，提取章节列表
 * 支持中文章节格式：第X章 标题：内容
 */
export function parseOutlineText(text: string): ParsedChapter[] {
  const items: ParsedChapter[] = []

  // 中文章节格式：第X章 标题：内容
  const patternCn = /(第\s*(\d+)\s*章\s*(.*?))\s*[:：\n]\s*([\s\S]*?)(?=(?:\n\s*第\s*\d+\s*章)|$)/g

  let match
  while ((match = patternCn.exec(text)) !== null) {
    const fullTitlePart = match[1].trim()
    const chapNum = parseInt(match[2])
    const titleOnly = (match[3] || '').trim()
    const contentPart = (match[4] || '').trim()

    // 清理标题，移除"第X章"前缀
    let titleClean = fullTitlePart.replace(/^第\d+章\s*/, '').trim()
    if (titleOnly) {
      titleClean = titleOnly
    }

    items.push({
      chapter: chapNum,
      title: titleClean,
      summary: contentPart,
    })
  }

  // 如果中文格式没匹配到，尝试英文格式
  if (items.length === 0) {
    const patternEn = /(?:Ch(?:apter)?\.?\s*)(\d+)\s*([^\n:：]*?)\s*[:：]\s*([\s\S]*?)(?=(?:\n\s*(?:Ch(?:apter)?\.?\s*\d+|第\s*\d+\s*章))|$)/gi

    while ((match = patternEn.exec(text)) !== null) {
      const chapNum = parseInt(match[1])
      const titleOnly = (match[2] || '').trim()
      const contentPart = (match[3] || '').trim()

      items.push({
        chapter: chapNum,
        title: titleOnly,
        summary: contentPart,
      })
    }
  }

  // 按章节号排序
  items.sort((a, b) => a.chapter - b.chapter)

  return items
}
