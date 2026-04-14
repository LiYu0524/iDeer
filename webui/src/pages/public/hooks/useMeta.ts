import { useEffect, useState } from 'react';
import type { PublicMeta } from '../../../lib/types';
import { getMeta } from '../../../lib/api';

const DEFAULT_META: PublicMeta = {
  github_url: 'https://github.com/LiYu0524/daily-recommender',
  twitter_enabled: false,
  mail_enabled: false,
};

export function useMeta() {
  const [meta, setMeta] = useState<PublicMeta>(DEFAULT_META);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    getMeta()
      .then((data) => { if (!cancelled) setMeta(data); })
      .catch(console.error)
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  return { meta, loading };
}
