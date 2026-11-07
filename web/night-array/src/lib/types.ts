export type ViewerMode = 'work' | 'stow' | 'standalone'
export type ViewerStyle = 'studio' | 'cad' | 'xray' | 'blueprint'
export type FinishId = 'titanium' | 'graphite' | 'oxblood'
export type QualityId = 'high' | 'balanced' | 'battery'
export type CameraId = 'hero' | 'front' | 'top' | 'side' | 'back' | 'dock' | 'trays' | 'display'

export type SectionState = { axis: 'x' | 'z'; t: number } | null

export type ViewerState = {
  mode: ViewerMode
  style: ViewerStyle
  finish: FinishId
  amber: number
  explode: number
  section: SectionState
  dims: boolean
  autorotate: boolean
  isolate: string | null
  selected: string | null
  quality: QualityId
  cinematic: boolean
}

export type Preset = {
  mode?: ViewerMode
  style?: ViewerStyle
  finish?: FinishId
  amber?: number
  explode?: number
  section?: 'x' | 'z' | null
  dims?: boolean
  camera?: CameraId
  dock?: string
  isolate?: string | null
  clearIsolate?: boolean
}

export const DEFAULT_STATE: ViewerState = {
  mode: 'work',
  style: 'studio',
  finish: 'titanium',
  amber: 0.8,
  explode: 0,
  section: null,
  dims: false,
  autorotate: false,
  isolate: null,
  selected: null,
  quality: 'high',
  cinematic: false,
}

export type LiveStatus = 'idle' | 'loading' | 'ready' | 'error'
