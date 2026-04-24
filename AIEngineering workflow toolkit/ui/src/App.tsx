import { Routes, Route, Navigate } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Dashboard from './pages/Dashboard'
import NewReview from './pages/NewReview'
import ReviewDetail from './pages/ReviewDetail'

export default function App() {
  return (
    <div className="flex h-full min-h-screen bg-gray-950">
      <Sidebar />
      <main className="flex-1 min-w-0 overflow-y-auto scrollbar-thin">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/new" element={<NewReview />} />
          <Route path="/reviews/:id" element={<ReviewDetail />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}
