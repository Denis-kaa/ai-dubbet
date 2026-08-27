#!/bin/bash

# Production Environment Configuration for AI Dubber Server
#!/bin/bash

# Server-Side Setup Script
# Run on the remote server after deployment

echo "=== Server Environment Setup ==="
echo "Setup directory: /opt/xadichai"

# Restart services
sudo supervisorctl restart ai-dubber-api ai-dubber-worker

echo ""
echo "✓ Services restarted"
echo ""
echo "Available environment variables:"
echo "  - OPENAI_API_KEY (from deployment input)"
echo "  - AZURE_SPEECH_KEY (from deployment input)"
echo "  - CLICK_MERCHANT_ID (optional)"
echo "  - CLICK_SERVICE_ID (optional)"
echo "  - CLICK_SECRET_KEY (optional)"
echo ""
echo "Check service status:"
echo "  sudo supervisorctl status"
echo ""
echo "View logs:"
echo "  sudo tail -f /var/log/ai-dubber/api.log"
echo "  sudo tail -f /var/log/ai-dubber/worker.log"
echo ""
echo "Rebuild nginx config:"
echo "  sudo nginx -t && sudo systemctl reload nginx"
