import { availableAPIs, languageMap } from './constant'

export interface Auth {
  type: supportedPlatforms
  [propName: string]: any
}

export function checkAuth(_auth: Auth): boolean {
  return true
}

export function forceNumber(val: any): number {
  return Number(val) || 0
}

export function getOptionList(map: Record<string, string>, from: 'key' | 'value' = 'key') {
  return from === 'key'
    ? Object.keys(map).map(key => ({
        label: key,
        value: map[key],
      }))
    : Object.values(map).map(key => ({
        label: key,
        value: key,
      }))
}

export const optionLists = {
  localLanguageList: [
    { label: 'English', value: 'en' },
    { label: '简体中文', value: 'zh-cn' },
  ],
  apiList: getOptionList(availableAPIs),
  replyLanguageList: getOptionList(languageMap, 'value'),
}

export const getLabel = (key: string) => `${key}Label`
export const getPlaceholder = (key: string) => `${key}Placeholder`
