import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { toISODate } from '../i18n/format'

/** «Сегодня» по серверу (APP_TIMEZONE и APP_FAKE_TODAY), а не по часам браузера. */
export function useServerToday() {
  const [today, setToday] = useState<string>(toISODate(new Date()))
  const [fake, setFake] = useState(false)
  useEffect(() => {
    api.GET('/api/v1/health').then((r) => {
      if (r.data) {
        setToday(r.data.today)
        setFake(r.data.fake_today)
      }
    })
  }, [])
  return { today, fake }
}
