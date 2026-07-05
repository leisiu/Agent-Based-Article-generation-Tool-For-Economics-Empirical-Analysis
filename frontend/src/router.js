import Home from './views/Home.vue'
import Projects from './views/Projects.vue'
import ProjectDetail from './views/ProjectDetail.vue'
import Settings from './views/Settings.vue'
import NotFound from './views/NotFound.vue'

const routes = [
  { path: '/', name: 'Home', component: Home },
  { path: '/projects', name: 'Projects', component: Projects },
  { path: '/project/:id', name: 'ProjectDetail', component: ProjectDetail },
  { path: '/settings', name: 'Settings', component: Settings },
  { path: '/:pathMatch(.*)*', name: 'NotFound', component: NotFound },
]

export default routes
