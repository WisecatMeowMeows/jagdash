class RequestSchema:
    REQUIRED_KEYS = ["capability", "payload"]

    @staticmethod
    def validate(request):
        if not isinstance(request, dict):
            raise ValueError("Request must be a dictionary")

        for key in RequestSchema.REQUIRED_KEYS:
            if key not in request:
                raise ValueError(f"Missing required field: {key}")

        return True