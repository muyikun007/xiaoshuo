'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import toast from 'react-hot-toast'

export default function CreateNovelPage() {
  const router = useRouter()
  const [title, setTitle] = useState('')
  const [type, setType] = useState('')
  const [theme, setTheme] = useState('')
  const [outline, setOutline] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!title || !type || !theme || !outline) {
      toast.error('请填写所有必填项')
      return
    }

    setIsLoading(true)

    try {
      const response = await fetch('/api/novels', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ title, type, theme, outline }),
      })

      const data = await response.json()

      if (!response.ok) {
        toast.error(data.error || '创建失败')
        return
      }

      toast.success('创建成功！')
      router.push(`/novel/${data.id}`)
    } catch (error) {
      toast.error('创建失败，请重试')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="max-w-3xl mx-auto px-4">
        <Card>
          <CardHeader>
            <CardTitle>手动创建小说</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-6">
              <div>
                <label className="block text-sm font-medium mb-2">
                  作品名称 <span className="text-red-500">*</span>
                </label>
                <Input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="请输入作品名称"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">
                  作品类型 <span className="text-red-500">*</span>
                </label>
                <Input
                  value={type}
                  onChange={(e) => setType(e.target.value)}
                  placeholder="例如：都市、官场、商战、重生等"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">
                  主题设定 <span className="text-red-500">*</span>
                </label>
                <Input
                  value={theme}
                  onChange={(e) => setTheme(e.target.value)}
                  placeholder="请简要描述主题设定"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">
                  大纲内容 <span className="text-red-500">*</span>
                </label>
                <textarea
                  value={outline}
                  onChange={(e) => setOutline(e.target.value)}
                  placeholder="请粘贴完整的大纲内容，包含章节信息（第X章 标题：内容）"
                  className="w-full h-64 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  required
                />
                <p className="mt-2 text-sm text-gray-500">
                  大纲格式示例：第1章 标题：章节内容梗概...
                </p>
              </div>

              <div className="flex gap-3">
                <Button type="submit" disabled={isLoading}>
                  {isLoading ? '创建中...' : '创建作品'}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => router.back()}
                >
                  取消
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
