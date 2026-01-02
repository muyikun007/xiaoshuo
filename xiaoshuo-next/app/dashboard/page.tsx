import { redirect } from 'next/navigation'
import Link from 'next/link'
import { getCurrentUser } from '@/lib/auth-utils'
import { prisma } from '@/lib/db'
import { Nav } from '@/components/ui/nav'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatDate } from '@/lib/utils'

export default async function DashboardPage() {
  const user = await getCurrentUser()

  if (!user) {
    redirect('/login')
  }

  const novels = await prisma.novel.findMany({
    where: { userId: user.id },
    orderBy: { createdAt: 'desc' },
    include: {
      chapters: {
        select: {
          id: true,
          status: true,
        },
      },
    },
  })

  return (
    <div className="min-h-screen bg-gray-50">
      <Nav userBalance={user.tokenBalance} />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-3xl font-bold">我的作品</h1>
          <div className="flex gap-3">
            <Link href="/dashboard/generate-outline">
              <Button>
                <span className="mr-2">✨</span>
                AI 生成大纲
              </Button>
            </Link>
            <Link href="/dashboard/create-novel">
              <Button variant="outline">
                <span className="mr-2">➕</span>
                手动创建
              </Button>
            </Link>
          </div>
        </div>

        {novels.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center">
              <p className="text-gray-500 mb-4">暂无作品</p>
              <p className="text-sm text-gray-400">
                点击上方按钮开始创建您的第一部小说
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {novels.map((novel) => {
              const completedChapters = novel.chapters.filter(
                (c) => c.status === 'completed'
              ).length
              const totalChapters = novel.chapters.length

              return (
                <Card key={novel.id} className="hover:shadow-lg transition-shadow">
                  <CardHeader>
                    <CardTitle className="line-clamp-1">{novel.title}</CardTitle>
                    <p className="text-sm text-gray-500">{novel.type}</p>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2 text-sm text-gray-600">
                      <p>创建时间: {formatDate(novel.createdAt)}</p>
                      <p>
                        章节进度: {completedChapters}/{totalChapters}
                      </p>
                    </div>
                    <div className="mt-4 flex gap-2">
                      <Link href={`/novel/${novel.id}`} className="flex-1">
                        <Button variant="default" className="w-full" size="sm">
                          查看详情
                        </Button>
                      </Link>
                    </div>
                  </CardContent>
                </Card>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
