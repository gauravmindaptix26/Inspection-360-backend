from rest_framework import serializers
from .models import Employee, User, Project, UserTaskList

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["email", "mobile_no", "full_name", "password"]

    def create(self, validated_data):
        validated_data["user_type"] = 3
        return User.objects.create_user(**validated_data)



class ProjectSerializer(serializers.ModelSerializer):
    subProjects = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = ["id", "name", "parentProject", "subProjects", "isDeleted", "createdAt"]

    def get_subProjects(self, obj):
        sub_projects = obj.subProjects.filter(isDeleted=False)
        return ProjectSerializer(sub_projects, many=True).data
        
        
        
class UserSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "mobile_no",
            "full_name",
            "user_type",
            "is_active",
            "createdAt",
            "projectId",
        ]


class EmployeeSerializer(serializers.ModelSerializer):

    class Meta:
        model = Employee
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
