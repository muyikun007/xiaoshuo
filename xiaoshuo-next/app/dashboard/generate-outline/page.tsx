'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import toast from 'react-hot-toast'

const NOVEL_TYPES = [
  '都市', '官场', '商战', '重生', '逆袭',
  '职场', '豪门', '复仇', '权谋', '刑侦',
  '医疗', '科技', '金融', '娱乐圈', '体育',
]

export default function GenerateOutlinePage() {
  const router = useRouter()
  const [type, setType] = useState('')
  const [theme, setTheme] = useState('')
  const [isGenerating, setIsGenerating] = useState(false)
  const [outline, setOutline] = useState('')

  const handleGenerate = async () => {
    if (!type || !theme) {
      toast.error('请选择类型并输入主题')
      return
    }

    setIsGenerating(true)
    setOutline('')

    try {
      const response = await fetch('/api/generate/outline', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ type, theme }),
      })

      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.error || '生成失败')
      }

      // 流式读取大纲
      const reader = response.body?.getReader()
      const decoder = new TextDecoder()

      if (!reader) {
        throw new Error('无法读取响应流')
      }

      let accumulatedOutline = ''

      while (true) {
        const { done, value } = await reader.read()

        if (done) break

        const chunk = decoder.decode(value, { stream: true })
        accumulatedOutline += chunk
        setOutline(accumulatedOutline)
      }

      toast.success('大纲生成完成！')
    } catch (error: any) {
      toast.error(error.message || '生成失败')
    } finally {
      setIsGenerating(false)
    }
  }

  const handleSave = async () => {
    if (!outline) {
      toast.error('请先生成大纲')
      return
    }

    try {
      const title = `${type}-${new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`

      const response = await fetch('/api/novels', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ title, type, theme, outline }),
      })

      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.error || '保存失败')
      }

      toast.success('保存成功！')
      router.push(`/novel/${data.id}`)
    } catch (error: any) {
      toast.error(error.message || '保存失败')
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="max-w-5xl mx-auto px-4">
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>AI 智能大纲生成</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-6">
              <div>
                <label className="block text-sm font-medium mb-2">
                  选择小说类型 <span className="text-red-500">*</span>
                </label>
                <div className="grid grid-cols-3 md:grid-cols-5 gap-2">
                  {NOVEL_TYPES.map((t) => (
                    <button
                      key={t}
                      onClick={() => setType(t)}
                      className={`px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                        type === t
                          ? 'bg-blue-600 text-white'
                          : 'bg-gray-100 hover:bg-gray-200'
                      }`}
                    >
                      {t}
                    </button>
                  ))}
                </div>
                <div className="mt-2">
                  <Input
                    value={type}
                    onChange={(e) => setType(e.target.value)}
                    placeholder="或输入自定义类型"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">
                  主题设定 <span className="text-red-500">*</span>
                </label>
                <textarea
                  value={theme}
                  onChange={(e) => setTheme(e.target.value)}
                  placeholder="请描述小说的核心主题、主角设定、故事背景等（越详细越好）&#10;例如：一个底层公务员重生回20年前，利用未来记忆在官场步步为营，最终成为封疆大吏"
                  className="w-full h-32 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  required
                />
              </div>

              <div className="flex gap-3">
                <Button
                  onClick={handleGenerate}
                  disabled={isGenerating}
                  className="flex-1 md:flex-none"
                >
                  {isGenerating ? '生成中...' : '🎯 开始生成'}
                </Button>
                {outline && !isGenerating && (
                  <Button onClick={handleSave} variant="outline">
                    💾 保存作品
                  </Button>
                )}
                <Button variant="outline" onClick={() => router.back()}>
                  取消
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {(outline || isGenerating) && (
          <Card>
            <CardHeader>
              <CardTitle>生成的大纲</CardTitle>
            </CardHeader>
            <CardContent>
              <textarea
                value={outline}
                readOnly
                className="w-full h-96 p-3 border rounded-md bg-gray-50 font-mono text-sm"
                placeholder={isGenerating ? '正在生成中，请稍候...' : ''}
              />
              <p className="text-sm text-gray-500 mt-2">
                字数：{outline.length} | 状态：{isGenerating ? '生成中...' : '已完成'}
              </p>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}
