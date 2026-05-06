import type { AppRouteRecord } from '@/types/router'

const RAG_ROUTES: AppRouteRecord[] = [
  {
    name: 'RagChat_',
    path: '/rag-chat',
    component: '/index/index',
    meta: {
      title: 'menus.rag.chat',
      icon: '&#xe6c2;',
      order: 3
    },
    children: [
      {
        name: 'RagChat',
        path: '/rag-chat',
        component: '/rag/chat/index',
        meta: {
          title: 'menus.rag.chat',
          icon: '&#xe6c2;',
          keepAlive: true,
          isHide: false
        }
      }
    ]
  },
  {
    name: 'RagDocuments_',
    path: '/rag-documents',
    component: '/index/index',
    meta: {
      title: 'menus.rag.documents',
      icon: '&#xe6df;',
      order: 4
    },
    children: [
      {
        name: 'RagDocuments',
        path: '/rag-documents',
        component: '/rag/documents/index',
        meta: {
          title: 'menus.rag.documents',
          icon: '&#xe6df;',
          keepAlive: false,
          isHide: false
        }
      }
    ]
  },
  {
    name: 'AiDaily',
    path: '/ai/daily',
    component: '/ai/daily/index',
    meta: {
      title: 'menus.rag.daily',
      icon: '&#xe710;',
      order: 2
    }
  }
]

export default RAG_ROUTES
