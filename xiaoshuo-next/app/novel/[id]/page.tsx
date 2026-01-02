import { redirect } from 'next/navigation'
import { getCurrentUser } from '@/lib/auth-utils'
import { prisma } from '@/lib/db'
import { Nav } from '@/components/ui/nav'
import { ChapterList } from '@/components/novel/chapter-list'

interface NovelPageProps {
  params: {
    id: string
  }
}

export default async function NovelPage({ params }: NovelPageProps) {
  const user = await getCurrentUser()

  if (!user) {
    redirect('/login')
  }

  const novel = await prisma.novel.findUnique({
    where: { id: parseInt(params.id) },
    include: {
      chapters: {
        orderBy: { chapterNum: 'asc' },
      },
    },
  })

  if (!novel || novel.userId !== user.id) {
    redirect('/dashboard')
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Nav userBalance={user.tokenBalance} />

      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-6">
          <h1 className="text-3xl font-bold mb-2">{novel.title}</h1>
          <div className="flex gap-4 text-sm text-gray-600">
            <span>类型: {novel.type}</span>
            <span>·</span>
            <span>章节数: {novel.chapters.length}</span>
          </div>
          {novel.theme && (
            <p className="mt-3 text-gray-700">{novel.theme}</p>
          )}
        </div>

        <ChapterList
          novelId={novel.id}
          novelType={novel.type || ''}
          novelTheme={novel.theme || ''}
          novelOutline={novel.outline || ''}
          chapters={novel.chapters}
          userBalance={user.tokenBalance}
        />
      </div>
    </div>
  )
}
