'use client'

import { useState } from 'react'
import { ChapterItem } from './chapter-item'

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

interface ChapterListProps {
  novelId: number
  novelType: string
  novelTheme: string
  novelOutline: string
  chapters: Chapter[]
  userBalance: number
}

export function ChapterList({
  novelId,
  novelType,
  novelTheme,
  novelOutline,
  chapters,
  userBalance,
}: ChapterListProps) {
  const [chapterStates, setChapterStates] = useState<Record<number, Chapter>>(
    chapters.reduce((acc, chapter) => {
      acc[chapter.id] = chapter
      return acc
    }, {} as Record<number, Chapter>)
  )

  const updateChapter = (chapterId: number, updates: Partial<Chapter>) => {
    setChapterStates((prev) => ({
      ...prev,
      [chapterId]: {
        ...prev[chapterId],
        ...updates,
      },
    }))
  }

  return (
    <div className="space-y-4">
      {chapters.map((chapter, index) => {
        const prevChapter = index > 0 ? chapters[index - 1] : null
        const currentState = chapterStates[chapter.id] || chapter

        return (
          <ChapterItem
            key={chapter.id}
            chapter={currentState}
            novelId={novelId}
            novelType={novelType}
            novelTheme={novelTheme}
            novelOutline={novelOutline}
            prevChapterContent={prevChapter?.content || ''}
            userBalance={userBalance}
            onUpdate={updateChapter}
          />
        )
      })}
    </div>
  )
}
