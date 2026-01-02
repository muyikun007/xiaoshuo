import Link from 'next/link'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { redirect } from 'next/navigation'

export default async function HomePage() {
  const session = await getServerSession(authOptions)

  if (session) {
    redirect('/dashboard')
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100">
      <div className="max-w-4xl mx-auto px-4 text-center">
        <h1 className="text-6xl font-bold text-gray-900 mb-6">
          小说大纲生成器
        </h1>
        <p className="text-xl text-gray-700 mb-8">
          AI驱动的中文网络小说大纲和内容生成工具
        </p>
        <p className="text-lg text-gray-600 mb-12">
          支持40+小说类型 · 智能大纲生成 · 章节内容创作 · 3-5分钟出纲
        </p>

        <div className="flex gap-4 justify-center">
          <Link
            href="/login"
            className="px-8 py-3 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-700 transition-colors"
          >
            登录
          </Link>
          <Link
            href="/register"
            className="px-8 py-3 bg-white text-blue-600 border-2 border-blue-600 rounded-lg font-semibold hover:bg-blue-50 transition-colors"
          >
            注册账号
          </Link>
        </div>

        <div className="mt-16 grid grid-cols-1 md:grid-cols-3 gap-8">
          <div className="bg-white p-6 rounded-lg shadow-md">
            <div className="text-4xl mb-4">📝</div>
            <h3 className="text-xl font-semibold mb-2">AI智能大纲</h3>
            <p className="text-gray-600">
              基于类型和主题，自动生成完整小说大纲，包含人设、世界观、章节梗概
            </p>
          </div>
          <div className="bg-white p-6 rounded-lg shadow-md">
            <div className="text-4xl mb-4">✍️</div>
            <h3 className="text-xl font-semibold mb-2">章节内容生成</h3>
            <p className="text-gray-600">
              根据大纲智能生成章节正文，2000字以上，剧情连贯，人物鲜活
            </p>
          </div>
          <div className="bg-white p-6 rounded-lg shadow-md">
            <div className="text-4xl mb-4">⚡</div>
            <h3 className="text-xl font-semibold mb-2">高效创作</h3>
            <p className="text-gray-600">
              流式输出，实时预览，大幅提升创作效率，告别灵感枯竭
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
