from rest_framework import serializers


class LoginSerializer(serializers.Serializer):
    # Accept either a unified identifier or separate email/username fields.
    identifier = serializers.CharField(required=False, allow_blank=False, trim_whitespace=True)
    email = serializers.CharField(required=False, allow_blank=False, trim_whitespace=True)
    username = serializers.CharField(required=False, allow_blank=False, trim_whitespace=True)
    role = serializers.IntegerField(required=False)
    password = serializers.CharField(trim_whitespace=False)

    def validate(self, attrs):
        ident = attrs.get("identifier") or attrs.get("email") or attrs.get("username")
        if not ident:
            raise serializers.ValidationError({"identifier": "Provide email or username."})
        attrs["identifier"] = ident
        return attrs


class CreateAccountSerializer(serializers.Serializer):
    email = serializers.EmailField(trim_whitespace=True)
    username = serializers.CharField(trim_whitespace=True)
    customerPlanID = serializers.IntegerField()
    password = serializers.CharField(trim_whitespace=False)


class ForgotPasswordSerializer(serializers.Serializer):
    identifier = serializers.CharField(required=False, allow_blank=False, trim_whitespace=True)
    email = serializers.EmailField(required=False, allow_blank=False)
    username = serializers.CharField(required=False, allow_blank=False, trim_whitespace=True)

    def validate(self, attrs):
        ident = attrs.get("identifier") or attrs.get("email") or attrs.get("username")
        if not ident:
            raise serializers.ValidationError({"identifier": "Provide email or username."})
        attrs["identifier"] = ident
        return attrs


class ResetPasswordSerializer(serializers.Serializer):
    token = serializers.CharField(trim_whitespace=True)
    new_password = serializers.CharField(trim_whitespace=False, min_length=8)
