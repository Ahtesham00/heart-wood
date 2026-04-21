const API_BASE = "/api/sessions";

class ServerAPI {
    static async createSession(layer, brief) {
        const res = await fetch(`${API_BASE}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ layer: parseInt(layer), brief })
        });
        if (!res.ok) throw new Error("Failed to create session");
        return res.json();
    }

    static async getSession(sessionId) {
        const res = await fetch(`${API_BASE}/${sessionId}`);
        if (!res.ok) throw new Error("Failed to get session state");
        return res.json();
    }

    static async submitReview(sessionId, acceptedIds, overridesObj) {
        const res = await fetch(`${API_BASE}/${sessionId}/review`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                accepted: acceptedIds,
                overrides: overridesObj
            })
        });
        return res.json();
    }
}
