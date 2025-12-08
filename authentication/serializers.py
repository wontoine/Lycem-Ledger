from rest_framework import serializers


class LoginSerializer(serializers.Serializer):
    """
    Serializer for processing user login requests.
    It supports multiple input methods (unified identifier, email, or username)
    to provide flexibility for the frontend.
    """
    # Accept either a unified identifier string or specific email/username fields.
    # required=False allows the client to send just one of these fields.
    identifier = serializers.CharField(required=False, allow_blank=False, trim_whitespace=True)
    email = serializers.CharField(required=False, allow_blank=False, trim_whitespace=True)
    username = serializers.CharField(required=False, allow_blank=False, trim_whitespace=True)

    # Optional field to specify a role during login if necessary (e.g., for multi-role portals)
    role = serializers.IntegerField(required=False)

    # Passwords should not be trimmed of whitespace to preserve exact user input.
    password = serializers.CharField(trim_whitespace=False)

    def validate(self, attrs):
        """
        Check that at least one identification field was provided and normalize
        it into a single 'identifier' key for the backend to use.
        """
        # Resolve the login identity from any of the three possible input fields
        ident = attrs.get("identifier") or attrs.get("email") or attrs.get("username")

        if not ident:
            raise serializers.ValidationError({"identifier": "Provide email or username."})

        # Normalize the result so the view only needs to look at 'identifier'
        attrs["identifier"] = ident
        return attrs


class CreateAccountSerializer(serializers.Serializer):
    """
    Serializer for registering a new user.
    Enforces required fields including the specific plan ID they are signing up for.
    """
    email = serializers.EmailField(trim_whitespace=True)
    username = serializers.CharField(trim_whitespace=True)
    # The ID of the insurance plan the customer is subscribing to upon creation
    customerPlanID = serializers.IntegerField()
    # Ensure password retains significant whitespace
    password = serializers.CharField(trim_whitespace=False)


class ForgotPasswordSerializer(serializers.Serializer):
    """
    Serializer to initiate a password reset request.
    Allows the user to identify themselves via username, email, or a generic identifier.
    """
    identifier = serializers.CharField(required=False, allow_blank=False, trim_whitespace=True)
    email = serializers.EmailField(required=False, allow_blank=False)
    username = serializers.CharField(required=False, allow_blank=False, trim_whitespace=True)

    def validate(self, attrs):
        """
        Ensure a valid user identifier is present.
        """
        # Prioritize 'identifier', fall back to 'email', then 'username'
        ident = attrs.get("identifier") or attrs.get("email") or attrs.get("username")

        if not ident:
            raise serializers.ValidationError({"identifier": "Provide email or username."})

        # Standardize key for the view logic
        attrs["identifier"] = ident
        return attrs


class ResetPasswordSerializer(serializers.Serializer):
    """
    Serializer for the final step of the password reset workflow.
    Validates the secure token and enforces password complexity rules.
    """
    # The secure token previously sent to the user (via email/SMS)
    token = serializers.CharField(trim_whitespace=True)
    # Enforce minimum length of 8 chars for security
    new_password = serializers.CharField(trim_whitespace=False, min_length=8)