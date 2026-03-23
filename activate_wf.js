const axios = require('axios');

async function activateWorkflow() {
  try {
    // Try local n8n database activation
    const response = await axios.put(
      'http://localhost:5678/api/v1/workflows/K1oYnk42BB1F0M8Y',
      { active: true },
      {
        headers: {
          'Content-Type': 'application/json',
          'X-N8N-API-KEY': ''
        }
      }
    );
    console.log('Workflow activated:', response.data.active);
  } catch (error) {
    console.log('Error:', error.message);
  }
}

activateWorkflow();
