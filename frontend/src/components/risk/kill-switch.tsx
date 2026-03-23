'use client';

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import axios from 'axios';

async function activateKillSwitch() {
  await axios.post((process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000') + '/api/risk/kill-switch');
}

export function KillSwitch() {
  const [confirm, setConfirm] = useState(false);
  const [activated, setActivated] = useState(false);
  const [loading, setLoading] = useState(false);

  async function handleActivate() {
    setLoading(true);
    await activateKillSwitch();
    setActivated(true);
    setLoading(false);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-destructive">Emergency Kill Switch</CardTitle>
      </CardHeader>
      <CardContent>
        {activated ? (
          <div className="text-green-600 font-bold">Kill switch activated. All orders cancelled.</div>
        ) : confirm ? (
          <div>
            <p className="mb-4 text-muted-foreground">Are you sure? This will cancel all open orders and block new trades.</p>
            <Button variant="destructive" size="lg" onClick={handleActivate} disabled={loading}>
              {loading ? 'Activating...' : 'Confirm Kill Switch'}
            </Button>
            <Button variant="ghost" className="ml-2" onClick={() => setConfirm(false)} disabled={loading}>
              Cancel
            </Button>
          </div>
        ) : (
          <div>
            <p className="mb-4 text-muted-foreground">Activate the kill switch in case of emergency only.</p>
            <Button variant="destructive" size="lg" onClick={() => setConfirm(true)}>
              ACTIVATE KILL SWITCH
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
