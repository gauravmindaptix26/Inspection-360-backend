from rest_framework import serializers
from .models import User,Project,UserTaskList

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["email", "mobile_no", "full_name", "password"]

    def create(self, validated_data):
        validated_data["user_type"] = 3
        return User.objects.create_user(**validated_data)



class ProjectSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = Project
        fields = '__all__'
        
        
        
class UserSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = User
        fields = '__all__'
        
        
class UserTaskListSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = UserTaskList
        fields = '__all__'
        
        
class UserTagListSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = UserTaskList
        fields = ['markTag']
        
        
        
        
        
        
class UploadImageSerializer(serializers.Serializer):
    image = serializers.FileField()
