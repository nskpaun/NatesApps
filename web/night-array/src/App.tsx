import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Shell } from './components/Shell'
import { ViewerPark } from './components/Stage'
import { Explore } from './screens/Explore'
import { Board, Story } from './screens/Story'
import { Studio } from './screens/Studio'
import { DrawingPage, Files, GroupPage } from './screens/Files'
import { Specs } from './screens/Specs'
import { Night } from './screens/Night'

export function App() {
  return (
    <BrowserRouter>
      <ViewerPark />
      <Routes>
        <Route element={<Shell />}>
          <Route index element={<Explore />} />
          <Route path="story/:id" element={<Story />} />
          <Route path="board" element={<Board />} />
          <Route path="studio" element={<Studio />} />
          <Route path="files" element={<Files />} />
          <Route path="files/:groupId" element={<GroupPage />} />
          <Route path="files/:groupId/drawing" element={<DrawingPage />} />
          <Route path="specs" element={<Specs />} />
          <Route path="specs/:section" element={<Specs />} />
          <Route path="night" element={<Night />} />
          <Route path="*" element={<Explore />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
