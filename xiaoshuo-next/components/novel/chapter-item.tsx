'use client'

import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import toast from 'react-hot-toast'

interface Chapter {
  id: number
  chapterNum: number
  title: string | null
  summary: string | null
  content: string | null
  status: string
  wordCount: number
  cost: number
}

interface ChapterItemProps {
  chapter: Chapter
  novelId: number
  novelType: string
  novelTheme: string
  novelOutline: string
  prevChapterContent: string
  userBalance: number
  onUpdate: (chapterId: number, updates: Partial<Chapter>) => void
}

export function ChapterItem({
  chapter,
  novelId,
  novelType,
  novelTheme,
  novelOutline,
  prevChapterContent,
  userBalance,
  onUpdate,
}: ChapterItemProps) {
  const [isGenerating, setIsGenerating] = useState(false)
  const [content, setContent] = useState(chapter.content || '')

  useEffect(() => {
    setContent(chapter.content || '')
  }, [chapter.content])

  const handleGenerate = async () => {
    if (userBalance < 1000) {
      toast.error('余额不足，请充值')
      return
    }

    if (!confirm(`确定要生成第${chapter.chapterNum}章吗？预计消耗约1000积分`)) {
      return
    }

    setIsGenerating(true)
    onUpdate(chapter.id, { status: 'generating' })

    try {
      const response = await fetch(`/api/chapters/${chapter.id}/generate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          novelType,
          novelTheme,
          novelOutline,
          prevContent: prevChapterContent,
        }),
      })

      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.error || '生成失败')
      }

      // 使用流式读取
      const reader = response.body?.getReader()
      const decoder = new TextDecoder()

      if (!reader) {
        throw new Error('无法读取响应流')
      }

      let accumulatedContent = ''

      while (true) {
        const { done, value } = await reader.read()

        if (done) break

        const chunk = decoder.decode(value, { stream: true })
        accumulatedContent += chunk
        setContent(accumulatedContent)
      }

      // 生成完成，更新状态
      const statusResponse = await fetch(`/api/chapters/${chapter.id}/status`)
      const statusData = await statusResponse.json()

      onUpdate(chapter.id, {
        content: statusData.content,
        status: statusData.status,
        wordCount: statusData.wordCount,
        cost: statusData.cost,
      })

      toast.success('生成完成！')
    } catch (error: any) {
      toast.error(error.message || '生成失败')
      onUpdate(chapter.id, { status: 'pending' })
    } finally {
      setIsGenerating(false)
    }
  }

  const getStatusText = () => {
    switch (chapter.status) {
      case 'pending':
        return '待生成'
      case 'generating':
        return '生成中...'
      case 'completed':
        return '已完成'
      default:
        return chapter.status
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex justify-between items-start">
          <div>
            <CardTitle>
              第{chapter.chapterNum}章 {chapter.title || ''}
            </CardTitle>
            <p className="text-sm text-gray-500 mt-1">
              状态: {getStatusText()}
            </p>
          </div>
          {chapter.status !== 'completed' && (
            <Button
              onClick={handleGenerate}
              disabled={isGenerating || chapter.status === 'generating'}
              size="sm"
            >
              {isGenerating ? '生成中...' : '生成正文'}
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {chapter.summary && (
          <div className="mb-4">
            <p className="text-sm text-gray-600">梗概：{chapter.summary}</p>
          </div>
        )}

        {(content || chapter.status === 'completed') && (
          <div className="mt-4">
            <textarea
              className="w-full h-64 p-3 border rounded-md bg-gray-50 font-mono text-sm"
              value={content}
              readOnly
            />
            {chapter.status === 'completed' && (
              <p className="text-sm text-gray-500 mt-2">
                字数: {chapter.wordCount} | 消耗: {chapter.cost} 积分
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
