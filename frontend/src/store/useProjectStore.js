import { defineStore } from 'pinia'

export const useProjectStore = defineStore('project', {
  state: () => ({
    projects: [],
    currentProject: null,
    loading: false,
  }),
  actions: {
    setProjects(projects) {
      this.projects = projects
    },
    setCurrentProject(project) {
      this.currentProject = project
    },
    setLoading(loading) {
      this.loading = loading
    },
  },
})
