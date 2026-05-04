import type { AppRouteRecord } from '@/router/types'

const RAG_ROUTES: AppRouteRecord[] = [
  {
    name: 'Rag',
    path: '/rag',
    component: '/index/index',
    meta: {
      title: 'menus.rag.title',
      icon: '&#xe6c2;',
      order: 10
    },
    children: [
      {
        name: 'RagChat',
        path: '/rag/chat',
        component: '/rag/chat/index',
        meta: {
          title: 'menus.rag.chat',
          icon: '&#xe6c2;',
          keepAlive: false
        }
      },
      {
        name: 'RagDocuments',
        path: '/rag/documents',
        component: '/rag/documents/index',
        meta: {
          title: 'menus.rag.documents',
          icon: '&#xe6df;',
          keepAlive: false
        }
      }
    ]
  }
]

export default RAG_ROUTES
